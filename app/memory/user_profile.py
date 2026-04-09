import json
import sqlite3
from datetime import datetime
from app.config import SQLITE_DB_PATH

class UserProfileManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or SQLITE_DB_PATH

    def get_profile(self, user_id: str) -> dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT psychological_profile FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return {}
        return {}

    def update_profile(self, user_id: str, mood: str = None, cause: str = None,
                       preferred_genres: list = None, liked_track: str = None,
                       recommendations: list = None, care_note: str = None):
        profile = self.get_profile(user_id)

        if mood:
            history = profile.get("mood_history", [])
            history.append({"date": datetime.now().strftime("%Y-%m-%d"), "mood": mood, "cause": cause or ""})
            # 최근 20개만 유지
            profile["mood_history"] = history[-20:]

        if care_note:
            notes = profile.get("care_notes", [])
            notes.append(care_note)
            profile["care_notes"] = notes[-20:]

        if recommendations:
            prefs = profile.get("music_preferences", {})

            # preferred_genres: 장르 빈도 기반 업데이트
            genre_counts = {}
            for rec in recommendations:
                genre = rec.get("genre", "")
                if genre:
                    genre_counts[genre] = genre_counts.get(genre, 0) + 1
            if genre_counts:
                sorted_genres = sorted(genre_counts, key=genre_counts.get, reverse=True)
                existing = list(prefs.get("preferred_genres", []))
                for g in sorted_genres:
                    if g not in existing:
                        existing.append(g)
                prefs["preferred_genres"] = existing[:10]

            # acoustic_tendency: acousticness 평균
            acousticness_vals = [
                rec["acousticness"] for rec in recommendations
                if isinstance(rec.get("acousticness"), (int, float))
            ]
            if acousticness_vals:
                avg = sum(acousticness_vals) / len(acousticness_vals)
                prefs["acoustic_tendency"] = round(avg, 3)

            profile["music_preferences"] = prefs

        if preferred_genres:
            prefs = profile.get("music_preferences", {})
            existing = set(prefs.get("preferred_genres", []))
            existing.update(preferred_genres)
            prefs["preferred_genres"] = list(existing)[:10]
            profile["music_preferences"] = prefs

        if liked_track:
            prefs = profile.get("music_preferences", {})
            liked = prefs.get("liked_tracks", [])
            if liked_track not in liked:
                liked.append(liked_track)
            prefs["liked_tracks"] = liked[-20:]
            profile["music_preferences"] = prefs

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE users SET psychological_profile = ? WHERE user_id = ?",
                  (json.dumps(profile, ensure_ascii=False), user_id))
        conn.commit()
        conn.close()
