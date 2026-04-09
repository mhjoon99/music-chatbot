import pandas as pd

def get_mental_health_songs(df: pd.DataFrame, label: str, sort_by: str = "valence", limit: int = 20) -> dict:
    """특정 Mental Health Label 곡 조회"""
    filtered = df[df["Mental_Health_Label"].str.lower() == label.lower()]
    if filtered.empty:
        return {"tracks": [], "count": 0, "message": f"'{label}' 라벨 곡이 없습니다."}

    if sort_by in filtered.columns:
        filtered = filtered.sort_values(sort_by, ascending=True)

    result = filtered.head(limit)
    return {
        "tracks": [
            {"track_id": r["track_id"], "track_name": r["track_name"], "track_artist": r["track_artist"],
             "genre": r.get("playlist_subgenre", r["playlist_genre"]), "valence": float(r["valence"]), "energy": float(r["energy"]),
             "danceability": float(r.get("danceability", 0)), "tempo": float(r.get("tempo", 0)),
             "acousticness": float(r.get("acousticness", 0)), "instrumentalness": float(r.get("instrumentalness", 0)),
             "speechiness": float(r.get("speechiness", 0)), "loudness": float(r.get("loudness", 0)),
             "liveness": float(r.get("liveness", 0)),
             "mental_health": r["Mental_Health_Label"]}
            for _, r in result.iterrows()
        ],
        "count": len(result)
    }
