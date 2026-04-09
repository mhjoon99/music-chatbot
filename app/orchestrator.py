import json
from concurrent.futures import ThreadPoolExecutor
from app.agents.gate_agent import GateAgent
from app.agents.music_agent import MusicAgent
from app.agents.care_agent import CareAgent
from app.tools.tool_executor import ToolExecutor
from app.spotify.spotify_client import SpotifyClient, is_spotify_available
from app.guardrails.safety import EMERGENCY_RESPONSE, OFF_TOPIC_RESPONSE
from app.guardrails.output_validator import validate_response

# 사용자 감정 키워드 → valence/energy 추정 (LLM 호출 없이)
EMOTION_MAP = {
    # 부정적 감정 (low valence)
    "우울": (0.15, 0.25), "슬프": (0.15, 0.3), "슬픔": (0.15, 0.3), "눈물": (0.1, 0.2),
    "외로": (0.2, 0.2), "공허": (0.2, 0.2), "멍": (0.25, 0.2), "무기력": (0.15, 0.15),
    "불안": (0.25, 0.5), "초조": (0.25, 0.55), "긴장": (0.3, 0.5), "걱정": (0.3, 0.4),
    "화나": (0.15, 0.7), "분노": (0.1, 0.75), "짜증": (0.2, 0.6), "혼나": (0.2, 0.5),
    "좌절": (0.15, 0.45), "스트레스": (0.2, 0.55), "지치": (0.25, 0.2), "피곤": (0.3, 0.15),
    "힘들": (0.2, 0.3), "속상": (0.2, 0.35),
    # 긍정적 감정 (high valence)
    "신나": (0.85, 0.85), "행복": (0.8, 0.7), "기쁘": (0.8, 0.7), "좋아": (0.7, 0.6),
    "설레": (0.75, 0.65), "즐거": (0.8, 0.75), "흥분": (0.8, 0.85), "기분 좋": (0.75, 0.6),
    "편안": (0.55, 0.3), "차분": (0.5, 0.25), "평화": (0.6, 0.2), "여유": (0.6, 0.3),
    "감사": (0.7, 0.4), "뿌듯": (0.7, 0.5), "성취": (0.75, 0.6),
}

def estimate_user_emotion(user_message: str, gate_result: dict) -> dict:
    """사용자 메시지에서 감정 상태(valence/energy) 추정. LLM 호출 없음."""
    intent = gate_result.get("intent", "emotion")

    # situation/similar는 감정이 아닌 요청이므로 None 반환
    if intent != "emotion":
        return {"valence": None, "energy": None, "label": intent}

    # 키워드 매칭
    msg = user_message.lower()
    matched_v, matched_e, count = 0.0, 0.0, 0
    for keyword, (v, e) in EMOTION_MAP.items():
        if keyword in msg:
            matched_v += v
            matched_e += e
            count += 1

    if count > 0:
        return {"valence": round(matched_v / count, 2), "energy": round(matched_e / count, 2), "label": "emotion"}

    # 매칭 실패 시 중립
    return {"valence": 0.5, "energy": 0.5, "label": "emotion"}


class MindTuneOrchestrator:
    def __init__(self, df, embedder=None, collection=None):
        self.gate = GateAgent()
        self.spotify = SpotifyClient()
        tool_executor = ToolExecutor(df=df, spotify=self.spotify, embedder=embedder, collection=collection)
        self.music = MusicAgent(tool_executor=tool_executor)
        self.care = CareAgent()

    def process(self, user_message: str, profile: dict = None, history: str = "",
                on_progress=None) -> dict:
        """전체 파이프라인 실행: Gate → Music → Care
        on_progress: callable(message: str) — 진행 상태 콜백 (streamlit st.write 등)
        """
        def _progress(msg):
            if on_progress:
                on_progress(msg)

        # Step 1: Gate — 분류 + 안전 체크
        _progress("🛡️ 메시지 분석 중...")
        print(f"[Gate] 분석 시작: '{user_message[:50]}...'", flush=True)
        gate_result = self.gate.run(user_message)
        print(f"[Gate] 결과: intent={gate_result.get('intent')}, safety={gate_result.get('safety_flag')}, complexity={gate_result.get('complexity')}", flush=True)

        intent = gate_result.get("intent", "emotion")
        # Intent별 진행 메시지
        INTENT_MESSAGES = {
            "emotion": {
                "search": "💭 감정에 어울리는 곡을 찾고 있어요...",
                "react": "🎵 마음을 달래줄 최적의 추천을 만들고 있어요...",
                "care": "🤗 따뜻한 응답을 준비하고 있어요...",
            },
            "situation": {
                "search": "🔎 상황에 딱 맞는 BGM을 찾고 있어요...",
                "react": "🎶 분위기에 어울리는 플레이리스트를 구성 중이에요...",
                "care": "✨ 추천 메시지를 다듬고 있어요...",
            },
            "similar": {
                "search": "🔍 비슷한 느낌의 곡을 검색하고 있어요...",
                "react": "🎯 유사도를 분석하며 최적의 곡을 고르고 있어요...",
                "care": "📝 추천 이유를 정리하고 있어요...",
            },
        }
        msgs = INTENT_MESSAGES.get(intent, INTENT_MESSAGES["emotion"])

        if gate_result.get("safety_flag") == "danger":
            print("[Gate] 위험 신호 감지 → 긴급 응답", flush=True)
            return {
                "response": EMERGENCY_RESPONSE,
                "gate_result": gate_result,
                "tool_log": [],
                "iterations": 0
            }

        if gate_result.get("safety_flag") == "off_topic":
            print("[Gate] 범위 외 질문 → 안내 응답", flush=True)
            return {
                "response": OFF_TOPIC_RESPONSE,
                "gate_result": gate_result,
                "tool_log": [],
                "iterations": 0
            }

        # Step 1.5: 감정 추정 (Music Agent에 힌트 전달용)
        user_emotion = estimate_user_emotion(user_message, gate_result)
        if user_emotion.get("valence") is not None:
            gate_result["user_emotion"] = user_emotion
            print(f"[Emotion] valence={user_emotion['valence']}, energy={user_emotion['energy']}", flush=True)

        # Step 2: Music Agent — ReAct 루프
        _progress(msgs["search"])
        print("[Music] ReAct 루프 시작...", flush=True)
        music_result = self.music.run(
            user_message=user_message,
            gate_result=gate_result,
            profile=profile,
            history=history
        )
        tool_log = music_result.get("tool_log", [])
        print(f"[Music] 완료: {music_result.get('iterations', 0)}회 반복, {len(tool_log)}개 도구 호출", flush=True)
        for t in tool_log:
            print(f"  └─ {t['tool']}() → {t.get('result_count', '?')}건", flush=True)
        raw_len = len(music_result.get("final_response", ""))
        print(f"[Music] 원본 응답 길이: {raw_len}자", flush=True)
        _progress(msgs["react"])

        # Step 3: Spotify 검색 → Care Agent streaming 준비
        music_raw = music_result.get("final_response", "")

        # 추천 곡 목록 추출 (Spotify 검색용)
        recs = []
        if music_raw:
            try:
                data = json.loads(music_raw)
                recs = data.get("recommendations", [])
            except (json.JSONDecodeError, TypeError):
                pass

        # Spotify 검색 (빠름, 먼저 완료)
        spotify_results = {}
        if recs and is_spotify_available():
            _progress(msgs["care"])
            print(f"[Spotify] {len(recs)}곡 병렬 검색 시작...", flush=True)
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = {}
                for rec in recs:
                    name = rec.get("track_name", "")
                    artist = rec.get("track_artist", "")
                    if name and artist:
                        futures[pool.submit(self.spotify.spotify_search, name, artist)] = name
                for future in futures:
                    track_name = futures[future]
                    try:
                        spotify_results[track_name] = future.result(timeout=10)
                    except Exception as e:
                        print(f"[Spotify] ⚠️ '{track_name}' 타임아웃/오류: {e}", flush=True)
                        spotify_results[track_name] = {"found": False}
            print(f"[Spotify] 병렬 검색 완료: {sum(1 for v in spotify_results.values() if v.get('found'))}/{len(spotify_results)}곡 매칭", flush=True)

        # Care Agent streaming generator 준비 (Streamlit에서 소비)
        care_stream = None
        if music_raw:
            care_stream = self.care.run_stream(
                music_result=music_result,
                gate_result=gate_result,
                user_message=user_message,
                history=history
            )

        # Spotify 결과를 music_raw JSON에 병합
        enriched_raw = music_raw
        if recs and spotify_results:
            try:
                data = json.loads(music_raw)
                for rec in data.get("recommendations", []):
                    name = rec.get("track_name", "")
                    sp = spotify_results.get(name, {})
                    if sp.get("found"):
                        rec["spotify_url"] = sp.get("spotify_url")
                        rec["preview_url"] = sp.get("preview_url")
                        rec["album_art"] = sp.get("album_art")
                    elif sp.get("youtube_url"):
                        rec["youtube_url"] = sp.get("youtube_url")
                enriched_raw = json.dumps(data, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "response": "",  # streaming 모드에서는 빈 문자열
            "care_stream": care_stream,  # Streamlit에서 소비할 generator
            "gate_result": gate_result,
            "tool_log": tool_log,
            "iterations": music_result.get("iterations", 0),
            "music_raw": enriched_raw,
            "user_emotion": user_emotion
        }
