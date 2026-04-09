import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from app.config import DATA_PATH

FEATURE_COLS = [
    "danceability",
    "energy",
    "valence",
    "tempo_norm",
    "acousticness",
    "instrumentalness",
    "speechiness",
]

AUDIO_FEATURES = [
    "danceability",
    "energy",
    "valence",
    "tempo",
    "acousticness",
    "instrumentalness",
    "speechiness",
    "loudness",
    "liveness",
]


def load_and_preprocess(csv_path: str = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    # Deduplicate by track_id
    df = df.drop_duplicates(subset=["track_id"])

    # Deduplicate by track_name + track_artist
    df = df.drop_duplicates(subset=["track_name", "track_artist"])

    # Remove rows with empty track_name
    df = df[df["track_name"].notna() & (df["track_name"].str.strip() != "")]

    # Map null Mental_Health_Label to "Normal"
    df["Mental_Health_Label"] = df["Mental_Health_Label"].fillna("Normal")

    # Min-Max scale audio features
    scaler = MinMaxScaler()
    existing_features = [col for col in AUDIO_FEATURES if col in df.columns]
    df[existing_features] = scaler.fit_transform(df[existing_features])

    # tempo_norm: separate 0~1 normalized tempo column (tempo already scaled above)
    if "tempo" in df.columns:
        df["tempo_norm"] = df["tempo"]

    df = df.reset_index(drop=True)
    return df


def build_search_index(df: pd.DataFrame) -> dict:
    index: dict[str, list[int]] = {}
    for i, row in df.iterrows():
        key = str(row["track_name"]).lower()
        if key not in index:
            index[key] = []
        index[key].append(i)
    return index
