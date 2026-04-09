import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from app.tools.search_by_features import FEATURE_COLS

# 인텐트별 가중치: vector(벡터 유사도), feature(피처 유사도), popularity(인기도)
# emotion: feature(β=0.6) dominant → 감정은 valence/energy 수치가 핵심
# situation: balanced → 상황은 의미(벡터)+수치(피처) 둘 다 필요
# similar: vector(α=0.5) dominant → 원곡의 "느낌" 매칭이 중요
WEIGHTS = {
    "emotion": {"vector": 0.3, "feature": 0.6, "popularity": 0.1},
    "situation": {"vector": 0.4, "feature": 0.5, "popularity": 0.1},
    "similar": {"vector": 0.5, "feature": 0.4, "popularity": 0.1},
}

POPULARITY_KEYWORDS = {"유명", "인기", "popular", "히트", "대중적"}

def rerank_results(df: pd.DataFrame, intent: str, candidate_track_ids: list,
                   query_text: str = "", embedder=None, collection=None, top_k: int = 5) -> dict:
    """여러 검색 결과를 융합하여 최종 순위"""
    w = WEIGHTS.get(intent, WEIGHTS["emotion"]).copy()

    # 인기 키워드 감지 시 popularity 가중치 동적 상향 (0.1 → 0.4)
    if query_text and any(kw in query_text for kw in POPULARITY_KEYWORDS):
        original_pop = w["popularity"]
        boost = 0.4 - original_pop  # 추가 가중치
        total_non_pop = w["vector"] + w["feature"]
        w["vector"] -= boost * (w["vector"] / total_non_pop)
        w["feature"] -= boost * (w["feature"] / total_non_pop)
        w["popularity"] = 0.4

    candidates = df[df["track_id"].isin(candidate_track_ids)].copy()

    if candidates.empty:
        return {"tracks": [], "count": 0}

    # feature similarity (candidates 간 평균 벡터와의 유사도)
    feat_matrix = candidates[FEATURE_COLS].values
    centroid = feat_matrix.mean(axis=0).reshape(1, -1)
    candidates["feat_score"] = cosine_similarity(feat_matrix, centroid).flatten()

    # vector similarity (ChromaDB에서 query_text 유사도) — 배치 조회로 N+1 해소
    candidates["vec_score"] = 0.5  # 기본값
    if query_text and collection is not None and embedder is not None:
        try:
            query_emb = embedder.encode(query_text)
            all_ids = candidates["track_id"].tolist()
            batch_result = collection.get(ids=all_ids, include=["embeddings"])
            if batch_result and batch_result["embeddings"]:
                id_to_emb = {
                    batch_result["ids"][i]: np.array(batch_result["embeddings"][i])
                    for i in range(len(batch_result["ids"]))
                }
                for idx, row in candidates.iterrows():
                    doc_emb = id_to_emb.get(row["track_id"])
                    if doc_emb is not None:
                        sim = cosine_similarity(query_emb.reshape(1, -1), doc_emb.reshape(1, -1))[0][0]
                        candidates.at[idx, "vec_score"] = float(sim)
        except Exception:
            pass

    # popularity score (0~1 정규화)
    pop_col = "track_popularity" if "track_popularity" in candidates.columns else None
    if pop_col:
        max_pop = candidates[pop_col].max()
        candidates["pop_score"] = candidates[pop_col] / max_pop if max_pop > 0 else 0
    else:
        candidates["pop_score"] = 0.5

    # 최종 점수 계산
    candidates["final_score"] = (
        w["vector"] * candidates["vec_score"] +
        w["feature"] * candidates["feat_score"] +
        w["popularity"] * candidates["pop_score"]
    )

    result = candidates.nlargest(top_k, "final_score")
    return {
        "tracks": [
            {"track_id": r["track_id"], "track_name": r["track_name"], "track_artist": r["track_artist"],
             "genre": r.get("playlist_subgenre", r["playlist_genre"]), "valence": float(r["valence"]), "energy": float(r["energy"]),
             "tempo": float(r["tempo"]), "final_score": float(r["final_score"]),
             "mental_health": r.get("Mental_Health_Label", "Normal")}
            for _, r in result.iterrows()
        ],
        "count": len(result)
    }
