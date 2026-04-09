# 상황별 오디오 피처 프리셋 테이블
SITUATION_PRESETS = {
    "카페": {"danceability_range": [0, 0.6], "energy_range": [0.2, 0.5], "acousticness_min": 0.5,
             "instrumentalness_min": 0.2, "speechiness_max": 0.1, "tempo_range": [70, 110],
             "genre": ["pop", "r&b"]},
    "파티": {"danceability_range": [0.7, 1.0], "energy_range": [0.5, 0.8],
             "tempo_range": [100, 130], "genre": ["pop", "latin", "edm"]},
    "코딩": {"energy_range": [0.3, 0.6], "instrumentalness_min": 0.4,
             "speechiness_max": 0.05, "tempo_range": [80, 120], "genre": ["edm", "r&b"]},
    "운동": {"danceability_range": [0.7, 1.0], "energy_range": [0.8, 1.0],
             "acousticness_min": None, "tempo_range": [120, 200], "genre": ["edm", "rap"]},
    "비오는날": {"danceability_range": [0, 0.5], "energy_range": [0.2, 0.5], "acousticness_min": 0.5,
                "speechiness_max": 0.1, "tempo_range": [60, 100], "genre": ["pop", "r&b", "rock"]},
    "드라이브": {"danceability_range": [0.6, 1.0], "energy_range": [0.6, 0.9],
                "tempo_range": [100, 140], "genre": ["pop", "rock", "latin"]},
    "수면": {"danceability_range": [0, 0.4], "energy_range": [0, 0.3], "acousticness_min": 0.6,
             "instrumentalness_min": 0.5, "speechiness_max": 0.05, "tempo_range": [40, 80],
             "genre": ["r&b", "pop"]},
}

def get_preset(situation: str) -> dict | None:
    """상황 키워드 매칭으로 프리셋 반환"""
    for key, preset in SITUATION_PRESETS.items():
        if key in situation:
            # None 값 제거 후 반환
            return {k: v for k, v in preset.items() if v is not None}
    return None
