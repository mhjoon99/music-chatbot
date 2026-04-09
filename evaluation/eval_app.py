#!/usr/bin/env python3
"""MindTune Streamlit 평가 페이지 — A(적합도), D(자연스러움), F(Tool Calling) 수동 채점"""

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

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import json
import time
from datetime import datetime
from pathlib import Path
from app.config import DATA_PATH
from app.data.loader import load_and_preprocess
from app.data.embedder import load_descriptions, build_chroma_db
from app.orchestrator import MindTuneOrchestrator

FORBIDDEN_PHRASES = ["치료합니다", "치료할 수 있", "진단", "장애가 있", "병이 있", "처방"]

st.set_page_config(page_title="MindTune 평가", page_icon="📊", layout="wide")

# ── 시스템 초기화 ──
@st.cache_resource
def init_system():
    df = load_and_preprocess(DATA_PATH)
    descriptions = load_descriptions()
    embedder, collection = build_chroma_db(df, descriptions)
    orchestrator = MindTuneOrchestrator(df=df, embedder=embedder, collection=collection)
    return df, orchestrator

@st.cache_data
def load_queries():
    with open("evaluation/eval_queries.json", "r", encoding="utf-8") as f:
        return json.load(f)

def load_existing_results():
    results_dir = Path("evaluation/results")
    manual_files = sorted(results_dir.glob("manual_eval_*.json"), reverse=True)
    if manual_files:
        with open(manual_files[0], "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_results(results):
    os.makedirs("evaluation/results", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"evaluation/results/manual_eval_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return path

# ── 메인 ──
st.title("📊 MindTune 수동 평가")
st.caption("A. 추천 적합도 | D. 대화 자연스러움 | F. Tool Calling 정확도")

try:
    df, orchestrator = init_system()
    queries = load_queries()
    system_ready = True
except Exception as e:
    system_ready = False
    st.error(f"시스템 초기화 실패: {str(e)}")
    st.stop()

# ── 세션 상태 ──
if "eval_results" not in st.session_state:
    st.session_state.eval_results = load_existing_results()
if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0
if "current_response" not in st.session_state:
    st.session_state.current_response = None

# ── 사이드바: 진행 상황 ──
with st.sidebar:
    st.header("진행 상황")
    evaluated = len(st.session_state.eval_results)
    total = len(queries)
    st.progress(evaluated / total if total > 0 else 0)
    st.text(f"{evaluated} / {total} 완료")

    st.divider()

    # 카테고리 필터
    category = st.selectbox("카테고리 필터", ["전체", "emotion", "situation", "similar"])
    if category != "전체":
        filtered_queries = [q for q in queries if q["category"] == category]
    else:
        filtered_queries = queries

    st.divider()

    # 결과 요약
    if st.session_state.eval_results:
        st.header("현재 점수 요약")
        scores_a = [r["score_a"] for r in st.session_state.eval_results.values() if "score_a" in r]
        scores_d = [r["score_d"] for r in st.session_state.eval_results.values() if "score_d" in r]
        scores_f = [r["score_f"] for r in st.session_state.eval_results.values() if "score_f" in r]

        if scores_a:
            avg_a = sum(scores_a) / len(scores_a)
            st.metric("A. 추천 적합도", f"{avg_a:.1f}/5", delta="PASS" if avg_a >= 3.5 else "FAIL")
        if scores_d:
            avg_d = sum(scores_d) / len(scores_d)
            st.metric("D. 자연스러움", f"{avg_d:.1f}/5", delta="PASS" if avg_d >= 3.5 else "FAIL")
        if scores_f:
            avg_f = sum(scores_f) / len(scores_f)
            st.metric("F. Tool Calling", f"{avg_f:.1f}/5", delta="PASS" if avg_f >= 4.0 else "FAIL")

    st.divider()

    if st.button("💾 결과 저장"):
        path = save_results(st.session_state.eval_results)
        st.success(f"저장 완료: {path}")

# ── 쿼리 선택 ──
if not filtered_queries:
    st.info("해당 카테고리에 쿼리가 없습니다.")
    st.stop()

# 쿼리 네비게이션
col_nav1, col_nav2, col_nav3 = st.columns([1, 3, 1])
with col_nav1:
    if st.button("⬅ 이전"):
        st.session_state.current_idx = max(0, st.session_state.current_idx - 1)
        st.session_state.current_response = None
        st.rerun()
with col_nav3:
    if st.button("다음 ➡"):
        st.session_state.current_idx = min(len(filtered_queries) - 1, st.session_state.current_idx + 1)
        st.session_state.current_response = None
        st.rerun()
with col_nav2:
    st.session_state.current_idx = st.slider(
        "쿼리 선택", 0, len(filtered_queries) - 1, st.session_state.current_idx,
        format=f"#%d / {len(filtered_queries)}"
    )

q = filtered_queries[st.session_state.current_idx]
q_id = str(q["id"])

# ── 쿼리 정보 ──
st.divider()
st.subheader(f"#{q['id']} [{q['category']}] {q.get('difficulty', '')}")
st.markdown(f"**쿼리:** {q['query']}")
st.caption(f"기대 Intent: `{q['expected_intent']}` | {q.get('description', '')}")

# ── 실행 ──
if st.button("🚀 이 쿼리 실행", type="primary"):
    with st.status("실행 중...", expanded=True) as status:
        st.write("🛡️ Gate Agent 분석 중...")
        progress_placeholder = st.empty()
        def on_progress(msg):
            progress_placeholder.write(msg)

        start = time.time()
        result = orchestrator.process(q["query"], on_progress=on_progress)
        elapsed = time.time() - start
        progress_placeholder.empty()
        st.write(f"✅ 완료 ({elapsed:.1f}초)")
        status.update(label=f"✅ 완료 ({elapsed:.1f}초)", state="complete")

    st.session_state.current_response = {
        "result": result,
        "latency": round(elapsed, 2)
    }

# ── 결과 표시 + 채점 ──
if st.session_state.current_response:
    result = st.session_state.current_response["result"]
    latency = st.session_state.current_response["latency"]

    col_result, col_score = st.columns([3, 2])

    with col_result:
        st.markdown("### 응답")

        # Gate 결과
        gate = result.get("gate_result", {})
        intent_match = "✅" if gate.get("intent") == q["expected_intent"] else "❌"
        st.markdown(f"**Gate:** intent=`{gate.get('intent')}` {intent_match} | safety=`{gate.get('safety_flag')}` | complexity=`{gate.get('complexity')}`")
        st.markdown(f"**Latency:** {latency}s | **Iterations:** {result.get('iterations', 0)} | **Tools:** {len(result.get('tool_log', []))}")

        # 도구 호출 로그
        with st.expander("🔧 Tool 호출 로그"):
            for t in result.get("tool_log", []):
                st.text(f"  {t.get('tool', '?')}() → {t.get('result_count', '?')}건")

        # Care Agent 응답
        st.markdown("**Care Agent 응답:**")
        response = result.get("response", "")
        if response:
            st.markdown(response)
        else:
            st.warning("Care Agent 응답 없음")

        # 출력 가드레일 체크
        violations = [p for p in FORBIDDEN_PHRASES if p in response]
        if violations:
            st.error(f"❌ 출력 가드레일: FAIL (위반: {', '.join(violations)})")
        else:
            st.success("✅ 출력 가드레일: PASS")

        # 감정 추정 표시
        user_emotion = result.get("user_emotion")
        if user_emotion and (user_emotion.get("valence") is not None or user_emotion.get("energy") is not None):
            valence = user_emotion.get("valence")
            energy = user_emotion.get("energy")
            st.info(f"🧠 추정 감정: valence={valence}, energy={energy}")

        # Music Agent 원본
        with st.expander("🎵 Music Agent 원본"):
            music_raw = result.get("music_raw", "")
            if music_raw:
                try:
                    st.json(json.loads(music_raw))
                except json.JSONDecodeError:
                    st.code(music_raw[:1000])
            else:
                st.text("원본 응답 없음")

    with col_score:
        st.markdown("### 채점")

        # 기존 점수 로드
        existing = st.session_state.eval_results.get(q_id, {})

        score_a = st.slider(
            "A. 추천 적합도 (1~5)",
            1, 5, existing.get("score_a", 3),
            help="1=전혀 무관, 2=약간 관련, 3=보통, 4=적합, 5=매우 적합"
        )

        score_d = st.slider(
            "D. 대화 자연스러움 (1~5)",
            1, 5, existing.get("score_d", 3),
            help="1=매우 부자연스러움, 2=어색, 3=보통, 4=자연스러움, 5=매우 자연스러움"
        )

        score_f = st.slider(
            "F. Tool Calling 정확도 (1~5)",
            1, 5, existing.get("score_f", 3),
            help="1=완전 잘못된 도구, 2=불필요한 호출 많음, 3=보통, 4=적절, 5=최적"
        )

        notes = st.text_area("메모", existing.get("notes", ""))

        if st.button("✅ 채점 저장", type="primary"):
            st.session_state.eval_results[q_id] = {
                "query_id": q["id"],
                "query": q["query"],
                "category": q["category"],
                "expected_intent": q["expected_intent"],
                "actual_intent": gate.get("intent", ""),
                "score_a": score_a,
                "score_d": score_d,
                "score_f": score_f,
                "notes": notes,
                "latency": latency,
                "tool_count": len(result.get("tool_log", [])),
                "iterations": result.get("iterations", 0),
                "timestamp": datetime.now().isoformat()
            }
            st.success("채점 저장됨!")
            st.rerun()

# ── 하단: 전체 결과 테이블 ──
if st.session_state.eval_results:
    st.divider()
    st.subheader("📋 채점 결과 목록")
    rows = []
    for qid, data in sorted(st.session_state.eval_results.items(), key=lambda x: int(x[0])):
        rows.append({
            "ID": data.get("query_id", qid),
            "카테고리": data.get("category", ""),
            "쿼리": data.get("query", "")[:30] + "...",
            "A.적합도": data.get("score_a", "-"),
            "D.자연스러움": data.get("score_d", "-"),
            "F.ToolCall": data.get("score_f", "-"),
            "Latency": f"{data.get('latency', 0)}s",
        })
    st.dataframe(rows, use_container_width=True)
