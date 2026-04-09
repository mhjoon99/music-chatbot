import json
from openai import OpenAI
from app.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, MAX_REACT_ITERATIONS
from app.prompts.music_agent_prompt import build_music_agent_prompt

# Tool definitions (OpenAI-compatible Function Calling format)
MUSIC_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_by_features",
            "description": "오디오 피처 범위로 곡을 검색합니다. 감정이나 상황을 수치 조건으로 변환한 후 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "valence_range": {"type": "array", "items": {"type": "number"}, "description": "긍정도 범위 [min, max]"},
                    "energy_range": {"type": "array", "items": {"type": "number"}, "description": "에너지 범위 [min, max]"},
                    "tempo_range": {"type": "array", "items": {"type": "number"}, "description": "템포 범위 [min, max] (BPM)"},
                    "acousticness_min": {"type": "number", "description": "최소 어쿠스틱 수치"},
                    "instrumentalness_min": {"type": "number", "description": "최소 기악곡 수치"},
                    "speechiness_max": {"type": "number", "description": "최대 보컬 수치"},
                    "danceability_range": {"type": "array", "items": {"type": "number"}, "description": "댄서빌리티 범위"},
                    "genre": {"type": "array", "items": {"type": "string"}, "description": "장르 필터 (genre 또는 subgenre 모두 검색)"},
                    "mental_health_label": {"type": "array", "items": {"type": "string"}, "description": "MH Label 필터"},
                    "limit": {"type": "integer", "description": "최대 반환 곡 수 (기본 20)"}
                }, "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_description",
            "description": "자연어 설명으로 의미적으로 유사한 곡을 벡터 검색합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "자연어 검색 쿼리"},
                    "genre_filter": {"type": "array", "items": {"type": "string"}, "description": "장르 필터 (genre 또는 subgenre 모두 검색)"},
                    "top_k": {"type": "integer", "description": "반환 곡 수 (기본 20)"}
                }, "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_song",
            "description": "특정 곡의 상세 정보를 조회합니다. 유사곡 탐색 시 참조곡 확인용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "track_name": {"type": "string", "description": "곡명"},
                    "artist": {"type": "string", "description": "아티스트명 (선택)"}
                }, "required": ["track_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_mental_health_songs",
            "description": "특정 Mental Health Label이 지정된 곡을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Mental Health Label"},
                    "sort_by": {"type": "string", "description": "정렬 기준"},
                    "limit": {"type": "integer", "description": "최대 반환 곡 수"}
                }, "required": ["label"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rerank_results",
            "description": "여러 검색 결과를 융합하여 최종 순위를 매깁니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": ["emotion", "situation", "similar"], "description": "UseCase 타입"},
                    "candidate_track_ids": {"type": "array", "items": {"type": "string"}, "description": "후보 곡 track_id 리스트"},
                    "query_text": {"type": "string", "description": "원본 사용자 쿼리"},
                    "top_k": {"type": "integer", "description": "최종 반환 곡 수 (기본 5)"}
                }, "required": ["intent", "candidate_track_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "build_iso_playlist",
            "description": "동질 원리에 따라 곡 순서를 배열합니다. 현재 감정→목표 감정으로 점진적 이동.",
            "parameters": {
                "type": "object",
                "properties": {
                    "track_ids": {"type": "array", "items": {"type": "string"}, "description": "정렬할 곡 ID 리스트"},
                    "current_valence": {"type": "number", "description": "현재 감정 valence (0~1)"},
                    "target_valence": {"type": "number", "description": "목표 감정 valence (0~1)"},
                    "current_energy": {"type": "number", "description": "현재 감정 energy (0~1), 선택 사항"},
                    "target_energy": {"type": "number", "description": "목표 감정 energy (0~1), 선택 사항"},
                    "steps": {"type": "integer", "description": "플레이리스트 곡 수 (기본 5)"}
                }, "required": ["track_ids", "current_valence", "target_valence"]
            }
        }
    },
]


class MusicAgent:
    """Tool-Calling 기반 음악 추천 에이전트 (ReAct 루프)"""

    def __init__(self, tool_executor):
        self.client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        self.tools = MUSIC_AGENT_TOOLS
        self.executor = tool_executor
        self.max_iterations = MAX_REACT_ITERATIONS

    def run(self, user_message: str, gate_result: dict,
            profile: dict = None, history: str = "") -> dict:
        """ReAct 루프: 도구 자율 선택 → 실행 → 관찰 → 반복"""
        system_prompt = build_music_agent_prompt(gate_result, profile, history)
        use_thinking = gate_result.get("complexity") == "high"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        tool_call_log = []
        # 도구 결과 수집 (LLM 폴백 응답 생성용)
        collected = {"rerank": None, "iso": None}

        for iteration in range(self.max_iterations):
            print(f"[Music] ── 반복 {iteration+1}/{self.max_iterations} ──", flush=True)
            try:
                # Sliding window: system + user + last 8 tool-exchange messages (4 turns)
                llm_messages = messages[:2] + messages[2:][-8:] if len(messages) > 10 else messages
                response = self.client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=llm_messages,
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=1.0 if use_thinking else 0.7
                )
            except Exception as e:
                print(f"[Music] ❌ LLM 호출 오류: {str(e)[:100]}", flush=True)
                return {
                    "final_response": self._build_fallback_response(collected, gate_result),
                    "tool_log": tool_call_log,
                    "iterations": iteration + 1
                }

            choice = response.choices[0]
            print(f"[Music] finish_reason={choice.finish_reason}, tool_calls={len(choice.message.tool_calls or [])}", flush=True)

            # LLM의 사고 과정 (content가 있으면 표시)
            if choice.message.content:
                thought = choice.message.content[:200].replace('\n', ' ')
                print(f"[Music] 💭 LLM 사고: {thought}{'...' if len(choice.message.content) > 200 else ''}", flush=True)

            # 도구 호출 없이 텍스트 응답 → 완료
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                content = choice.message.content or ""
                # <think> 태그 제거
                if "<think>" in content:
                    content = content.split("</think>")[-1].strip()
                # ```json 코드블록 제거
                content = self._strip_code_block(content)
                print(f"[Music] 📝 최종 응답: {len(content)}자", flush=True)
                # LLM 응답이 너무 짧거나 유효한 JSON이 아니면 폴백
                if len(content) < 100 or not self._is_valid_recommendation_json(content):
                    fallback = self._build_fallback_response(collected, gate_result)
                    if fallback:
                        print(f"[Music] LLM 응답 부족({len(content)}자) → 폴백 응답 생성", flush=True)
                        content = fallback
                return {
                    "final_response": content,
                    "tool_log": tool_call_log,
                    "iterations": iteration + 1
                }

            # 도구 호출 처리
            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                func_name = tool_call.function.name
                try:
                    func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}

                # 주요 인자 요약 로그
                args_summary = ", ".join(f"{k}={str(v)[:30]}" for k, v in func_args.items())
                print(f"[Music] 🔧 호출: {func_name}({args_summary})", flush=True)

                # 도구 실행
                result = self.executor.execute(func_name, func_args)

                # Self-Verification: 검색 결과 곡 존재 여부 확인
                if func_name in ["search_by_features", "search_by_description"]:
                    result = self._verify_tracks(result)

                # 도구 결과 수집 (폴백용)
                if func_name == "rerank_results":
                    collected["rerank"] = result
                elif func_name == "build_iso_playlist":
                    collected["iso"] = result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })

                rc = result.get("count", len(result.get("tracks", result.get("playlist", []))))
                print(f"[Music]    → 결과: {rc}건", flush=True)

                tool_call_log.append({
                    "iteration": iteration + 1,
                    "tool": func_name,
                    "args": func_args,
                    "result_count": rc
                })

        # max_iterations 도달 — 수집된 결과로 폴백 시도
        fallback = self._build_fallback_response(collected, gate_result)
        return {
            "final_response": fallback or "추천을 준비하는 데 시간이 걸리고 있어요. 조금 더 구체적으로 알려주시면 더 빠르게 찾아드릴 수 있어요!",
            "tool_log": tool_call_log,
            "iterations": self.max_iterations
        }

    def _strip_code_block(self, content: str) -> str:
        """```json ... ``` 코드블록 감싸기 제거"""
        content = content.strip()
        if content.startswith("```"):
            # 첫 줄 제거 (```json 또는 ```)
            content = content.split("\n", 1)[-1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    def _is_valid_recommendation_json(self, content: str) -> bool:
        """응답이 recommendations를 포함한 유효한 JSON인지 확인"""
        try:
            cleaned = self._strip_code_block(content)
            data = json.loads(cleaned)
            recs = data.get("recommendations", [])
            return len(recs) > 0
        except (json.JSONDecodeError, TypeError):
            return False

    def _build_fallback_response(self, collected: dict, gate_result: dict) -> str:
        """수집된 도구 결과로 표준 JSON 응답 직접 구성"""
        # iso > rerank 순서로 트랙 소스 결정
        tracks = []
        iso_applied = False
        iso_direction = None

        if collected.get("iso") and collected["iso"].get("playlist"):
            tracks = collected["iso"]["playlist"]
            iso_applied = collected["iso"].get("iso_applied", False)
            iso_direction = collected["iso"].get("direction")
        elif collected.get("rerank") and collected["rerank"].get("tracks"):
            tracks = collected["rerank"]["tracks"]

        if not tracks:
            return ""

        recommendations = []
        for t in tracks:
            rec = {
                "track_name": t.get("track_name", ""),
                "track_artist": t.get("track_artist", ""),
                "genre": t.get("genre", t.get("playlist_genre", "")),
                "valence": t.get("valence", 0),
                "energy": t.get("energy", 0),
                "danceability": t.get("danceability", 0),
                "tempo": t.get("tempo", 0),
                "acousticness": t.get("acousticness", 0),
                "instrumentalness": t.get("instrumentalness", 0),
                "speechiness": t.get("speechiness", 0),
                "loudness": t.get("loudness", 0),
                "liveness": t.get("liveness", 0),
                "reason": t.get("iso_explanation", ""),
            }
            recommendations.append(rec)

        intent = gate_result.get("intent", "emotion") if gate_result else "emotion"
        analysis_map = {
            "emotion": "감정에 어울리는 곡을 선별했어요.",
            "situation": "상황에 맞는 곡을 찾았어요.",
            "similar": "비슷한 분위기의 곡을 모았어요.",
        }

        result = {
            "recommendations": recommendations,
            "iso_applied": iso_applied,
            "iso_direction": iso_direction,
            "analysis": analysis_map.get(intent, "추천 곡을 준비했어요.")
        }
        return json.dumps(result, ensure_ascii=False)

    def _verify_tracks(self, search_result: dict) -> dict:
        """검색 결과의 곡이 DB에 존재하는지 확인"""
        if "tracks" in search_result:
            verified = [t for t in search_result["tracks"] if self.executor.track_exists(t.get("track_id", ""))]
            search_result["tracks"] = verified
            search_result["count"] = len(verified)
        return search_result
