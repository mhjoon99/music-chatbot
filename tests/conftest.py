"""공유 테스트 픽스처"""
import os
import tempfile
import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def sample_df():
    """테스트용 샘플 DataFrame (10곡)"""
    np.random.seed(42)
    n = 10
    data = {
        "track_id": [f"tid_{i}" for i in range(n)],
        "track_name": [
            "Happy Song", "Sad Ballad", "Energetic Beat", "Calm Waves", "Dance Party",
            "Mellow Night", "Rock Anthem", "Jazz Cafe", "Lo-fi Chill", "Pop Hit"
        ],
        "track_artist": [
            "Artist A", "Artist B", "Artist C", "Artist D", "Artist E",
            "Artist F", "Artist G", "Artist H", "Artist I", "Artist J"
        ],
        "track_popularity": [80, 60, 90, 40, 95, 30, 70, 50, 65, 85],
        "playlist_genre": [
            "pop", "r&b", "edm", "r&b", "edm",
            "r&b", "rock", "r&b", "edm", "pop"
        ],
        "playlist_subgenre": [
            "dance pop", "neo soul", "electro house", "chill r&b", "big room",
            "quiet storm", "classic rock", "smooth jazz", "chillwave", "indie pop"
        ],
        "danceability": [0.8, 0.3, 0.9, 0.2, 0.95, 0.25, 0.6, 0.4, 0.35, 0.75],
        "energy": [0.7, 0.3, 0.95, 0.2, 0.9, 0.15, 0.85, 0.3, 0.25, 0.65],
        "valence": [0.9, 0.15, 0.8, 0.4, 0.85, 0.2, 0.5, 0.45, 0.3, 0.7],
        "tempo": [120, 70, 140, 60, 130, 65, 150, 90, 80, 110],
        "tempo_norm": [0.48, 0.28, 0.56, 0.24, 0.52, 0.26, 0.6, 0.36, 0.32, 0.44],
        "acousticness": [0.1, 0.7, 0.05, 0.8, 0.03, 0.85, 0.15, 0.6, 0.7, 0.2],
        "instrumentalness": [0.0, 0.1, 0.3, 0.5, 0.2, 0.6, 0.05, 0.4, 0.7, 0.0],
        "speechiness": [0.05, 0.04, 0.1, 0.03, 0.08, 0.02, 0.15, 0.03, 0.02, 0.06],
        "loudness": [-5, -12, -3, -18, -4, -20, -6, -14, -16, -7],
        "liveness": [0.1, 0.2, 0.15, 0.08, 0.3, 0.05, 0.4, 0.1, 0.06, 0.12],
        "Mental_Health_Label": [
            "Normal", "Depression", "Normal", "Normal", "Normal",
            "Depression", "Normal", "Normal", "PTSD", "Normal"
        ],
    }
    return pd.DataFrame(data)


@pytest.fixture
def tmp_db_path():
    """임시 SQLite DB 경로"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)
