import json
import pandas as pd
from app.tools.search_by_features import search_by_features
from app.tools.search_by_description import search_by_description
from app.tools.lookup_song import lookup_song
from app.tools.mental_health_songs import get_mental_health_songs
from app.tools.reranker import rerank_results
from app.tools.iso_playlist import build_iso_playlist
from app.spotify.spotify_client import SpotifyClient

class ToolExecutor:
    def __init__(self, df: pd.DataFrame, spotify: SpotifyClient = None, embedder=None, collection=None):
        self.df = df
        self.spotify = spotify or SpotifyClient()
        self.embedder = embedder
        self.collection = collection

    def execute(self, func_name: str, func_args: dict) -> dict:
        """도구 이름과 인자로 실제 도구 실행"""
        if func_name == "search_by_features":
            return search_by_features(self.df, func_args)
        elif func_name == "search_by_description":
            return search_by_description(
                query=func_args["query"],
                genre_filter=func_args.get("genre_filter"),
                top_k=func_args.get("top_k", 20)
            )
        elif func_name == "lookup_song":
            return lookup_song(self.df, func_args["track_name"], func_args.get("artist"))
        elif func_name == "get_mental_health_songs":
            return get_mental_health_songs(
                self.df, func_args["label"],
                sort_by=func_args.get("sort_by", "valence"),
                limit=func_args.get("limit", 20)
            )
        elif func_name == "rerank_results":
            return rerank_results(
                self.df, func_args["intent"], func_args["candidate_track_ids"],
                query_text=func_args.get("query_text", ""),
                embedder=self.embedder, collection=self.collection,
                top_k=func_args.get("top_k", 5)
            )
        elif func_name == "build_iso_playlist":
            return build_iso_playlist(
                self.df, func_args["track_ids"],
                func_args["current_valence"], func_args["target_valence"],
                steps=func_args.get("steps", 5),
                current_energy=func_args.get("current_energy"),
                target_energy=func_args.get("target_energy")
            )
        elif func_name == "spotify_search":
            return self.spotify.spotify_search(func_args["track_name"], func_args["artist"])
        else:
            return {"error": f"알 수 없는 도구: {func_name}"}

    def track_exists(self, track_id: str) -> bool:
        """track_id가 데이터셋에 존재하는지 확인"""
        return track_id in self.df["track_id"].values
