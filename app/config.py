import os
from dotenv import load_dotenv
load_dotenv()

# LLM settings
LLM_BASE_URL: str = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "")
LLM_MODEL: str = os.environ.get("LLM_MODEL", "")

# Spotify settings
SPOTIFY_CLIENT_ID: str = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET: str = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

# Data paths
DATA_PATH: str = os.environ.get("DATA_PATH", "data/Music_recommendation.csv")
CHROMA_DB_PATH: str = os.environ.get("CHROMA_DB_PATH", "data/chroma_db")
DESCRIPTIONS_CACHE_PATH: str = os.environ.get(
    "DESCRIPTIONS_CACHE_PATH", "data/song_descriptions.json"
)
SQLITE_DB_PATH: str = os.environ.get("SQLITE_DB_PATH", "data/mindtune.db")

# Embedding model
EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Agent settings
MAX_REACT_ITERATIONS: int = int(os.environ.get("MAX_REACT_ITERATIONS", "7"))
