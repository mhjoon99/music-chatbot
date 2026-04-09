FORBIDDEN_PHRASES = [
    "치료합니다", "치료할 수 있", "진단",
    "장애가 있", "병이 있", "처방"
]

def validate_response(response: str) -> str:
    """금지 표현 필터링"""
    for phrase in FORBIDDEN_PHRASES:
        if phrase in response:
            response = response.replace(phrase, "[부적절한 표현 제거됨]")
    return response

def verify_tracks_in_db(track_ids: list, df) -> list:
    """추천 곡이 실제 DB에 존재하는지 검증"""
    valid_ids = set(df["track_id"].values)
    return [tid for tid in track_ids if tid in valid_ids]
