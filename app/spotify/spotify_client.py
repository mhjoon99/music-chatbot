import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from urllib.parse import quote_plus
from app.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

# 모듈 레벨 상태 — 앱 시작 시 1회 체크, 이후 재사용
_spotify_available = None

def is_spotify_available() -> bool:
    """Spotify API가 실제로 동작하는지 반환 (앱 전역에서 사용)"""
    global _spotify_available
    if _spotify_available is None:
        _spotify_available = SpotifyClient()._check_availability()
    return _spotify_available


class SpotifyClient:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
                self._client = spotipy.Spotify(
                    client_credentials_manager=SpotifyClientCredentials(
                        client_id=SPOTIFY_CLIENT_ID,
                        client_secret=SPOTIFY_CLIENT_SECRET
                    )
                )
            else:
                self._client = None
        return self._client

    def _check_availability(self) -> bool:
        """테스트 검색 1회로 API 동작 여부 확인"""
        client = self._get_client()
        if client is None:
            print("[Spotify] API 키 미설정 — Spotify 기능 비활성", flush=True)
            return False
        try:
            client.search(q="test", type="track", limit=1)
            print("[Spotify] API 연결 성공", flush=True)
            return True
        except Exception as e:
            print(f"[Spotify] API 사용 불가 ({e}) — Spotify 기능 비활성", flush=True)
            return False

    def spotify_search(self, track_name: str, artist: str) -> dict:
        """Spotify에서 곡 검색"""
        if not is_spotify_available():
            return {"found": False, "reason": "Spotify API가 현재 사용 불가합니다."}

        client = self._get_client()
        query = f"track:{track_name} artist:{artist}"
        try:
            results = client.search(q=query, type="track", limit=1)
            if results["tracks"]["items"]:
                track = results["tracks"]["items"][0]
                print(f"[Spotify] ✅ '{track_name}' - {artist} → {track['external_urls']['spotify'][:50]}", flush=True)
                return {
                    "found": True,
                    "count": 1,
                    "spotify_url": track["external_urls"]["spotify"],
                    "preview_url": track.get("preview_url"),
                    "album_art": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                    "uri": track["uri"],
                    "track_name": track["name"],
                    "artist": track["artists"][0]["name"]
                }
            youtube_url = f"https://www.youtube.com/results?search_query={quote_plus(f'{track_name} {artist}')}"
            print(f"[Spotify] ❌ '{track_name}' - {artist} → 곡 없음 → YouTube 폴백", flush=True)
            return {"found": False, "count": 0, "reason": "Spotify에서 곡을 찾지 못했습니다.", "youtube_url": youtube_url}
        except Exception as e:
            youtube_url = f"https://www.youtube.com/results?search_query={quote_plus(f'{track_name} {artist}')}"
            print(f"[Spotify] ❌ '{track_name}' - {artist} → 오류: {str(e)[:80]} → YouTube 폴백", flush=True)
            return {"found": False, "count": 0, "reason": f"Spotify 검색 오류: {str(e)}", "youtube_url": youtube_url}

    # 데이터셋 서브장르 목록 (Music_recommendation.csv 기반)
    SUBGENRES = [
        "album rock", "big room", "classic rock", "dance pop", "electro house",
        "electropop", "gangster rap", "hard rock", "hip hop", "hip pop",
        "indie poptimism", "latin hip hop", "latin pop", "neo soul",
        "new jack swing", "permanent wave", "pop edm", "post-teen pop",
        "progressive electro house", "reggaeton", "southern hip hop",
        "trap", "tropical", "urban contemporary",
    ]

    def get_trending_tracks(self, limit: int = 3) -> list:
        """데이터셋 서브장르 중 랜덤 하나로 Spotify 인기곡 가져오기"""
        import random
        if not is_spotify_available():
            return []

        client = self._get_client()
        genre = random.choice(self.SUBGENRES)
        try:
            results = client.search(q=f'genre:"{genre}"', type="track", limit=limit)
            tracks = []
            for track in results.get("tracks", {}).get("items", [])[:limit]:
                tracks.append({
                    "track_name": track["name"],
                    "artist": ", ".join(a["name"] for a in track["artists"]),
                    "album_art": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                    "spotify_url": track["external_urls"]["spotify"],
                    "preview_url": track.get("preview_url"),
                    "genre": genre,
                })
            return tracks
        except Exception as e:
            print(f"[Spotify] 트렌딩 조회 실패: {e}", flush=True)
            return []
