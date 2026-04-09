import warnings
import logging
import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore", message=".*torchvision.*")
warnings.filterwarnings("ignore", message=".*Accessing.*__path__.*")
warnings.filterwarnings("ignore", message=".*CUDA initialization.*")
warnings.filterwarnings("ignore", message=".*GPU device discovery.*")
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("onnxruntime").setLevel(logging.ERROR)

import streamlit as st
import uuid
import json
import pandas as pd
import plotly.graph_objects as go

from app.config import DATA_PATH, CHROMA_DB_PATH, EMBEDDING_MODEL
from app.data.loader import load_and_preprocess
from app.data.embedder import load_descriptions, build_chroma_db
from app.orchestrator import MindTuneOrchestrator
from app.memory.conversation import ConversationManager
from app.memory.summarizer import Summarizer
from app.memory.user_profile import UserProfileManager
from app.guardrails.safety import EMERGENCY_RESPONSE
from app.spotify.spotify_client import is_spotify_available

# ── 페이지 설정 ──
st.set_page_config(page_title="MindTune", page_icon="🎵", layout="wide")

# ── 사용자 식별 (서버 측 파일 기반 — 안정적) ──
USER_ID_FILE = os.path.join(os.path.dirname(__file__), "data", ".user_id")

def get_or_create_user_id() -> str:
    """서버 측 파일에서 user_id를 읽거나, 없으면 새로 생성하여 저장.
    쿠키와 달리 브라우저/탭/새로고침에 무관하게 항상 동일한 ID를 반환."""
    if os.path.exists(USER_ID_FILE):
        with open(USER_ID_FILE, "r") as f:
            uid = f.read().strip()
            if uid:
                return uid
    new_id = str(uuid.uuid4())
    with open(USER_ID_FILE, "w") as f:
        f.write(new_id)
    return new_id

# ── 초기화 (캐싱) ──
@st.cache_resource
def init_system():
    """시스템 초기화: 데이터 로드, 벡터 DB, 오케스트레이터"""
    df = load_and_preprocess(DATA_PATH)
    descriptions = load_descriptions()
    embedder, collection = build_chroma_db(df, descriptions)
    orchestrator = MindTuneOrchestrator(df=df, embedder=embedder, collection=collection)
    return df, orchestrator, embedder, collection

# ── 세션 상태 초기화 (쿠키 기반) ──
if "user_id" not in st.session_state:
    st.session_state.user_id = get_or_create_user_id()
if "tool_logs" not in st.session_state:
    st.session_state.tool_logs = []
if "conv_manager" not in st.session_state:
    st.session_state.conv_manager = ConversationManager()
    st.session_state.user_id = st.session_state.conv_manager.get_or_create_user(st.session_state.user_id)
    # 재접속 시 이전 대화 요약 복원
    prev_summary = st.session_state.conv_manager.get_user_summary(st.session_state.user_id)
    conv_count = st.session_state.conv_manager.get_conversation_count(st.session_state.user_id)
    st.session_state.prev_summary = prev_summary
    st.session_state.is_returning_user = conv_count > 0
    # 기존 대화가 있으면 이어가기, 없으면 새로 생성
    latest_conv_id = st.session_state.conv_manager.get_latest_conversation(st.session_state.user_id)
    if latest_conv_id:
        st.session_state.conv_id = latest_conv_id
    else:
        st.session_state.conv_id = st.session_state.conv_manager.create_conversation(st.session_state.user_id)
if "messages" not in st.session_state:
    # DB에서 기존 메시지 복원 (새로고침/새 탭 대응)
    # 요약된 범위는 요약으로, 이후는 원본 메시지로 분리
    if "conv_id" in st.session_state and "conv_manager" in st.session_state:
        restored = st.session_state.conv_manager.get_summary_and_recent_messages(
            st.session_state.conv_id
        )
        st.session_state.conv_summary = restored["summary"]
        st.session_state.messages = restored["messages"]
    else:
        st.session_state.conv_summary = None
        st.session_state.messages = []
if "summarizer" not in st.session_state:
    st.session_state.summarizer = Summarizer()
if "profile_manager" not in st.session_state:
    st.session_state.profile_manager = UserProfileManager()

# ── 시스템 로드 ──
try:
    df, orchestrator, embedder, collection = init_system()
    system_ready = True
except Exception as e:
    system_ready = False
    st.error(f"시스템 초기화 실패: {str(e)}")

# ── 사이드바 ──
with st.sidebar:
    st.title("🎵 MindTune")
    st.caption("AI 기반 음악 심리 케어 에이전트")
    st.divider()
    st.caption("⚠️ MindTune은 전문 음악치료를 대체하지 않는 보조적 웰니스 도구입니다.")

    # 사용자 감정 변화 시각화: 턴별 사용자 감정 valence/energy 산점도
    emotion_points = st.session_state.get("emotion_history", [])
    if emotion_points:
        st.divider()
        st.caption("🧠 나의 감정 변화")
        fig = go.Figure(go.Scatter(
            x=[p["valence"] for p in emotion_points],
            y=[p["energy"] for p in emotion_points],
            mode="markers+lines+text",
            text=[str(p["turn"]) for p in emotion_points],
            textposition="top center",
            marker=dict(size=10, color="mediumpurple"),
            line=dict(color="mediumpurple", width=1, dash="dot"),
        ))
        fig.update_layout(
            xaxis_title="긍정도 (Valence)",
            yaxis_title="에너지 (Energy)",
            xaxis=dict(range=[0, 1]),
            yaxis=dict(range=[0, 1]),
            margin=dict(l=20, r=20, t=20, b=20),
            height=250,
        )
        st.plotly_chart(fig, use_container_width=True)

# ── 메인 채팅 영역 ──
st.title("🎵 MindTune")

# 환영 메시지 (항상 표시, 대화 기록과 분리 — DB 저장 X)
with st.chat_message("assistant"):
    if st.session_state.get("is_returning_user") and st.session_state.get("prev_summary"):
        st.markdown(f"""다시 오셨군요! **MindTune**이에요 🎵

지난 대화를 기억하고 있어요:
> {st.session_state.prev_summary}

이어서 음악 추천을 도와드릴게요. 오늘 기분은 어떠세요?

※ MindTune은 전문 음악치료를 대체하지 않는 보조적 웰니스 도구입니다.""")
    else:
        st.markdown("""안녕하세요! **MindTune**이에요 🎵

오늘 기분은 어떠세요? 음악으로 마음을 돌봐드릴게요.

이렇게 말씀해주시면 돼요:
- 😊 기분이나 감정을 알려주세요 (예: "오늘 좀 우울해")
- 🎧 상황을 설명해주세요 (예: "카페에서 책 읽을 때 BGM")
- 🔍 좋아하는 곡과 비슷한 곡을 찾아보세요 (예: "Coldplay Yellow 같은 곡")

※ MindTune은 전문 음악치료를 대체하지 않는 보조적 웰니스 도구입니다.""")

# 이전 대화 요약 표시 (요약된 범위가 있으면)
if st.session_state.get("conv_summary"):
    with st.chat_message("assistant"):
        st.markdown(f"📋 **이전 대화 요약:**\n> {st.session_state.conv_summary}")
        st.caption("⬆️ 이전 대화는 요약으로 표시됩니다. 아래부터 최근 대화입니다.")
    st.divider()

# 대화 히스토리 표시 (요약 이후 원본 메시지만)
assistant_idx = 0
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # 곡 카드 표시 (assistant 메시지에 spotify_data가 있으면)
        if msg["role"] == "assistant" and "spotify_data" in msg:
            for track in msg["spotify_data"]:
                if track.get("spotify_url"):
                    spotify_url = track["spotify_url"]
                    track_id = spotify_url.split("/track/")[-1].split("?")[0]
                    embed_html = f'<iframe src="https://open.spotify.com/embed/track/{track_id}" width="100%" height="80" frameborder="0" allow="encrypted-media" loading="lazy"></iframe>'
                    st.markdown(embed_html, unsafe_allow_html=True)
                elif track.get("youtube_url"):
                    track_name = track.get('track_name', track.get('name', ''))
                    artist = track.get('artist', track.get('track_artist', ''))
                    st.markdown(f"**{track_name}** - {artist}")
                    genre = track.get('genre') or track.get('playlist_genre') or track.get('playlist_subgenre') or '알 수 없음'
                    st.caption(f"장르: {genre}")
                    st.link_button("▶️ YouTube에서 듣기", track["youtube_url"])
                elif track.get("preview_url"):
                    st.audio(track["preview_url"])

        # 에이전트 동작 로그 토글
        if msg["role"] == "assistant":
            logs = st.session_state.tool_logs[assistant_idx] if assistant_idx < len(st.session_state.tool_logs) else []
            if logs:
                with st.expander("🔍 에이전트 동작 로그"):
                    for log_entry in logs:
                        tool_name = log_entry.get("tool", log_entry.get("name", "Unknown"))
                        params = log_entry.get("input", log_entry.get("params", {}))
                        result_val = log_entry.get("output", log_entry.get("result", ""))
                        st.markdown(f"**🔧 {tool_name}**")
                        st.caption(f"입력: {str(params)[:300]}")
                        st.caption(f"결과: {str(result_val)[:300]}")
                        st.divider()
            assistant_idx += 1

# 피드백 버튼 (대화가 있을 때만 표시)
if st.session_state.messages:
    feedback_cols = st.columns(4)
    with feedback_cols[0]:
        if st.button("🔥 더 신나게"):
            st.session_state.pending_input = "더 신나고 에너지 넘치는 곡으로 다시 추천해줘"
            st.rerun()
    with feedback_cols[1]:
        if st.button("🌙 더 차분하게"):
            st.session_state.pending_input = "더 차분하고 잔잔한 곡으로 다시 추천해줘"
            st.rerun()
    with feedback_cols[2]:
        if st.button("🔄 다른 장르"):
            st.session_state.pending_input = "다른 장르의 곡으로 추천해줘"
            st.rerun()
    with feedback_cols[3]:
        if st.button("🗑️ 대화 초기화"):
            st.session_state.messages = []
            st.session_state.tool_logs = []
            st.session_state.conv_id = st.session_state.conv_manager.create_conversation(st.session_state.user_id)
            st.rerun()

# ── 사용자 입력 처리 (채팅 입력 + 피드백 버튼 공통) ──
prompt = st.chat_input("기분이나 원하는 음악을 알려주세요...")
# 피드백 버튼에서 설정한 pending_input이 있으면 그것을 사용
if not prompt and "pending_input" in st.session_state:
    prompt = st.session_state.pending_input
    del st.session_state.pending_input
if prompt:
    if not system_ready:
        st.error("시스템이 아직 준비되지 않았습니다.")
    else:
        # 사용자 메시지 추가
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 대화 저장
        st.session_state.conv_manager.save_message(st.session_state.conv_id, "user", prompt)

        # 처리 중 표시
        with st.chat_message("assistant"):
            # 대기 중 트렌딩 곡 표시
            trending_placeholder = st.empty()
            if is_spotify_available():
                trending = orchestrator.spotify.get_trending_tracks(3)
                if trending:
                    with trending_placeholder.container():
                        genre_label = trending[0].get("genre", "music") if trending else "music"
                        st.caption(f"🔥 지금 인기 있는 {genre_label} 음악은?")
                        cols = st.columns(len(trending))
                        for col, t in zip(cols, trending):
                            with col:
                                if t.get("album_art"):
                                    st.image(t["album_art"], width=120)
                                st.markdown(f"**{t['track_name'][:20]}**")
                                st.caption(f"{t['artist'][:25]}")
                                if t.get("spotify_url"):
                                    track_id = t["spotify_url"].split("/")[-1].split("?")[0]
                                    st.components.v1.html(
                                        f'<iframe src="https://open.spotify.com/embed/track/{track_id}" '
                                        f'width="100%" height="80" frameborder="0" allow="encrypted-media" '
                                        f'loading="lazy"></iframe>',
                                        height=85
                                    )

            with st.status("🎵 음악을 찾고 있어요...", expanded=True) as status:
                status_container = st.empty()

                def on_progress(msg):
                    status_container.write(msg)

                # 프로필 및 히스토리 (현재 대화 요약 + 이전 세션 요약 결합)
                profile = st.session_state.profile_manager.get_profile(st.session_state.user_id)
                current_summary = st.session_state.conv_manager.get_latest_summary(st.session_state.conv_id)
                prev_summary = st.session_state.get("prev_summary", "")
                history_parts = [s for s in [prev_summary, current_summary] if s]
                history = " | ".join(history_parts) if history_parts else ""

                # 오케스트레이터 실행 (진행 상태 콜백 전달)
                result = orchestrator.process(prompt, profile=profile, history=history,
                                              on_progress=on_progress)

                status_container.write(f"🔍 도구 {len(result.get('tool_log', []))}회 호출 완료")
                status.update(label="✅ 추천 완료!", state="complete")

            # 추천 완료 후에도 트렌딩 카드 유지

            # 사용자 감정 히스토리 저장
            user_emotion = result.get("user_emotion", {})
            if user_emotion and user_emotion.get("valence") is not None:
                if "emotion_history" not in st.session_state:
                    st.session_state.emotion_history = []
                st.session_state.emotion_history.append({
                    "turn": len(st.session_state.emotion_history) + 1,
                    "valence": user_emotion["valence"],
                    "energy": user_emotion["energy"],
                })

            # 응답 표시
            response = result.get("response", "")
            music_raw = result.get("music_raw", "")

            # Care Agent 응답이 있으면 자연어로 표시
            if response and response.strip():
                st.markdown(response)
            else:
                # Care Agent 실패 → Music Agent JSON을 직접 파싱하여 카드로 표시
                displayed = False
                if music_raw and music_raw.strip():
                    try:
                        data = json.loads(music_raw)
                        recs = data.get("recommendations", [])
                        if recs:
                            analysis = data.get("analysis", "")
                            if analysis:
                                st.markdown(f"🎵 {analysis}")
                            st.markdown("---")
                            for i, track in enumerate(recs, 1):
                                if track.get("spotify_url"):
                                    spotify_url = track["spotify_url"]
                                    track_id = spotify_url.split("/track/")[-1].split("?")[0]
                                    embed_html = f'<iframe src="https://open.spotify.com/embed/track/{track_id}" width="100%" height="80" frameborder="0" allow="encrypted-media" loading="lazy"></iframe>'
                                    st.markdown(embed_html, unsafe_allow_html=True)
                                elif track.get("youtube_url"):
                                    st.markdown(f"**{track['track_name']}** — {track['track_artist']}")
                                    genre = track.get('genre') or track.get('playlist_genre') or track.get('playlist_subgenre') or '알 수 없음'
                                    st.caption(f"장르: {genre}")
                                    st.link_button("▶️ YouTube에서 듣기", track["youtube_url"])
                                elif track.get("preview_url"):
                                    st.audio(track["preview_url"])
                            if data.get("iso_applied"):
                                direction = "점점 밝아지는" if data.get("iso_direction") == "ascending" else "현재 감정에서 시작하는"
                                st.info(f"🎼 동질 원리 적용: {direction} 순서로 구성했어요.")
                            displayed = True
                            response = analysis or music_raw  # 저장용
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass

                if not displayed:
                    response = music_raw if music_raw else "죄송합니다, 추천을 생성하지 못했어요. 다시 시도해주세요."
                    st.markdown(response)

            # 메시지 저장 (spotify_data가 있으면 metadata로 함께 저장)
            msg_data = {"role": "assistant", "content": response}
            metadata = {}
            # result에서 spotify_data 추출
            spotify_tracks = result.get("spotify_data", [])
            if not spotify_tracks and music_raw:
                try:
                    data = json.loads(music_raw)
                    spotify_tracks = data.get("recommendations", [])
                except (json.JSONDecodeError, TypeError):
                    pass
            if spotify_tracks:
                msg_data["spotify_data"] = spotify_tracks
                metadata["spotify_data"] = spotify_tracks

            # 프로필 자동 갱신 (추천 결과 기반)
            recs_for_profile = []
            if music_raw:
                try:
                    _profile_data = json.loads(music_raw)
                    recs_for_profile = _profile_data.get("recommendations", [])
                except (json.JSONDecodeError, TypeError):
                    pass
            if not recs_for_profile:
                recs_for_profile = spotify_tracks
            if recs_for_profile:
                st.session_state.profile_manager.update_profile(
                    st.session_state.user_id,
                    recommendations=recs_for_profile
                )

            st.session_state.messages.append(msg_data)
            st.session_state.conv_manager.save_message(
                st.session_state.conv_id, "assistant", response, metadata=metadata or None
            )

            # 도구 로그 + 디버그 저장
            st.session_state.tool_logs.append(result.get("tool_log", []))
            st.session_state.last_result = result

            # 5턴마다 자동 요약
            msg_count = st.session_state.conv_manager.get_message_count(st.session_state.conv_id)
            if msg_count > 0 and msg_count % 10 == 0:  # 5턴 = 10메시지 (user+assistant)
                print(f"[Summary] 자동 요약 트리거: {msg_count}개 메시지 (5턴 도달)", flush=True)
                messages = st.session_state.conv_manager.get_messages(st.session_state.conv_id, limit=10)
                summary = st.session_state.summarizer.summarize(messages)
                st.session_state.conv_manager.save_summary(
                    st.session_state.conv_id, summary, f"1-{msg_count}")
                print(f"[Summary] 요약 저장 완료 (turn 1-{msg_count}):\n{summary}", flush=True)

