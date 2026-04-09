import pandas as pd

def lookup_song(df: pd.DataFrame, track_name: str, artist: str = None) -> dict:
    """특정 곡의 상세 정보 조회"""
    # 정확한 곡명 매칭 시도
    mask = df["track_name"].str.lower() == track_name.lower()
    if artist:
        mask &= df["track_artist"].str.lower() == artist.lower()
    matches = df[mask]
    if matches.empty:
        # 부분 매칭 시도
        mask = df["track_name"].str.lower().str.contains(track_name.lower(), na=False)
        if artist:
            mask &= df["track_artist"].str.lower().str.contains(artist.lower(), na=False)
        matches = df[mask]

    if matches.empty:
        return {"found": False, "message": f"'{track_name}' 곡을 데이터셋에서 찾지 못했습니다."}

    row = matches.iloc[0]
    return {
        "found": True,
        "track_id": row["track_id"],
        "track_name": row["track_name"],
        "track_artist": row["track_artist"],
        "genre": row["playlist_genre"],
        "subgenre": row.get("playlist_subgenre", ""),
        "energy": float(row["energy"]),
        "valence": float(row["valence"]),
        "tempo": float(row["tempo"]),
        "danceability": float(row["danceability"]),
        "acousticness": float(row["acousticness"]),
        "instrumentalness": float(row["instrumentalness"]),
        "speechiness": float(row["speechiness"]),
        "loudness": float(row.get("loudness", 0)),
        "liveness": float(row.get("liveness", 0)),
        "popularity": int(row.get("track_popularity", 0)),
        "mental_health": row.get("Mental_Health_Label", "Normal")
    }
