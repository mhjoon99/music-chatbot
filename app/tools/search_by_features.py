from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import pandas as pd

# 오디오 피처 컬럼 목록
FEATURE_COLS = ["danceability", "energy", "valence", "tempo_norm", "acousticness", "instrumentalness", "speechiness"]

def search_by_features(df: pd.DataFrame, params: dict) -> dict:
    """오디오 피처 범위 기반 검색 + 코사인 유사도 랭킹"""
    # Step 1: 범위 필터링
    mask = pd.Series(True, index=df.index)
    if params.get("valence_range"):
        mask &= df["valence"].between(*params["valence_range"])
    if params.get("energy_range"):
        mask &= df["energy"].between(*params["energy_range"])
    if params.get("tempo_range"):
        # tempo는 MinMaxScaler로 0~1 정규화됨 — BPM 입력값을 정규화하여 비교
        normalized_tempo = [v / 250.0 for v in params["tempo_range"]]
        mask &= df["tempo"].between(*normalized_tempo)
    if params.get("danceability_range"):
        mask &= df["danceability"].between(*params["danceability_range"])
    if params.get("genre"):
        genre_mask = df["playlist_genre"].isin(params["genre"])
        if "playlist_subgenre" in df.columns:
            genre_mask |= df["playlist_subgenre"].isin(params["genre"])
        mask &= genre_mask
    if params.get("acousticness_min"):
        mask &= df["acousticness"] >= params["acousticness_min"]
    if params.get("instrumentalness_min"):
        mask &= df["instrumentalness"] >= params["instrumentalness_min"]
    if params.get("speechiness_max"):
        mask &= df["speechiness"] <= params["speechiness_max"]
    if params.get("mental_health_label"):
        mask &= df["Mental_Health_Label"].isin(params["mental_health_label"])

    filtered = df[mask]
    if filtered.empty:
        return {"tracks": [], "count": 0}

    # Step 2: 코사인 유사도 (타겟 벡터 = 파라미터의 중앙값)
    target = build_target_vector(params)
    sims = cosine_similarity(filtered[FEATURE_COLS].values, target.reshape(1, -1)).flatten()
    filtered = filtered.copy()
    filtered["feature_similarity"] = sims
    result = filtered.nlargest(params.get("limit", 20), "feature_similarity")

    return {
        "tracks": [
            {"track_id": r["track_id"], "track_name": r["track_name"], "track_artist": r["track_artist"],
             "genre": r.get("playlist_subgenre", r["playlist_genre"]), "valence": float(r["valence"]), "energy": float(r["energy"]),
             "tempo": float(r["tempo"]), "acousticness": float(r["acousticness"]),
             "similarity": float(r["feature_similarity"]),
             "mental_health": r.get("Mental_Health_Label", "Normal")}
            for _, r in result.iterrows()
        ],
        "count": len(result)
    }

def build_target_vector(params: dict) -> np.ndarray:
    """파라미터에서 타겟 피처 벡터 생성 (범위의 중앙값 사용)"""
    defaults = {"danceability": 0.5, "energy": 0.5, "valence": 0.5, "tempo_norm": 0.5,
                "acousticness": 0.5, "instrumentalness": 0.0, "speechiness": 0.1}
    target = []
    for col in FEATURE_COLS:
        range_key = f"{col}_range" if col != "tempo_norm" else "tempo_range"
        if col == "tempo_norm" and params.get("tempo_range"):
            # tempo는 0~250 범위 가정, 정규화
            mid = sum(params["tempo_range"]) / 2
            target.append(mid / 250.0)
        elif params.get(range_key):
            target.append(sum(params[range_key]) / 2)
        elif params.get(f"{col}_min"):
            target.append(params[f"{col}_min"])
        elif params.get(f"{col}_max"):
            target.append(params[f"{col}_max"])
        else:
            target.append(defaults.get(col, 0.5))
    return np.array(target)
