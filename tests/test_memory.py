"""app/memory/ 모듈 단위 테스트"""
import pytest
from app.memory.conversation import ConversationManager
from app.memory.user_profile import UserProfileManager


# ── ConversationManager ───────────────────────────────────────────────

class TestConversationManager:
    @pytest.fixture
    def cm(self, tmp_db_path):
        return ConversationManager(db_path=tmp_db_path)

    def test_create_user(self, cm):
        user_id = cm.get_or_create_user("test_user")
        assert user_id == "test_user"

    def test_auto_generate_user_id(self, cm):
        user_id = cm.get_or_create_user()
        assert user_id is not None
        assert len(user_id) > 0

    def test_idempotent_user_creation(self, cm):
        cm.get_or_create_user("user1")
        cm.get_or_create_user("user1")  # 중복 호출 에러 없어야 함

    def test_create_conversation(self, cm):
        cm.get_or_create_user("user1")
        conv_id = cm.create_conversation("user1")
        assert conv_id is not None

    def test_save_and_get_messages(self, cm):
        cm.get_or_create_user("user1")
        conv_id = cm.create_conversation("user1")
        cm.save_message(conv_id, "user", "안녕하세요")
        cm.save_message(conv_id, "assistant", "반갑습니다!")
        messages = cm.get_messages(conv_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_message_count(self, cm):
        cm.get_or_create_user("user1")
        conv_id = cm.create_conversation("user1")
        assert cm.get_message_count(conv_id) == 0
        cm.save_message(conv_id, "user", "테스트")
        assert cm.get_message_count(conv_id) == 1

    def test_message_limit(self, cm):
        cm.get_or_create_user("user1")
        conv_id = cm.create_conversation("user1")
        for i in range(15):
            cm.save_message(conv_id, "user", f"메시지 {i}")
        messages = cm.get_messages(conv_id, limit=5)
        assert len(messages) == 5

    def test_save_and_get_summary(self, cm):
        cm.get_or_create_user("user1")
        conv_id = cm.create_conversation("user1")
        cm.save_summary(conv_id, "사용자가 우울한 기분에 대해 이야기함", "1-5")
        summary = cm.get_latest_summary(conv_id)
        assert "우울한" in summary

    def test_no_summary_returns_empty(self, cm):
        cm.get_or_create_user("user1")
        conv_id = cm.create_conversation("user1")
        assert cm.get_latest_summary(conv_id) == ""

    def test_get_latest_conversation(self, cm):
        cm.get_or_create_user("user1")
        conv1 = cm.create_conversation("user1")
        conv2 = cm.create_conversation("user1")
        latest = cm.get_latest_conversation("user1")
        assert latest == conv2

    def test_no_conversation_returns_none(self, cm):
        cm.get_or_create_user("user1")
        assert cm.get_latest_conversation("user1") is None

    def test_conversation_count(self, cm):
        cm.get_or_create_user("user1")
        assert cm.get_conversation_count("user1") == 0
        cm.create_conversation("user1")
        cm.create_conversation("user1")
        assert cm.get_conversation_count("user1") == 2

    def test_user_summary_across_conversations(self, cm):
        cm.get_or_create_user("user1")
        conv1 = cm.create_conversation("user1")
        cm.save_summary(conv1, "첫 대화 요약", "1-5")
        conv2 = cm.create_conversation("user1")
        cm.save_summary(conv2, "두번째 대화 요약", "1-5")
        summary = cm.get_user_summary("user1")
        assert "두번째" in summary


# ── UserProfileManager ────────────────────────────────────────────────

class TestUserProfileManager:
    @pytest.fixture
    def pm(self, tmp_db_path):
        # ConversationManager가 테이블 생성하므로 먼저 초기화
        ConversationManager(db_path=tmp_db_path).get_or_create_user("user1")
        return UserProfileManager(db_path=tmp_db_path)

    def test_empty_profile(self, pm):
        profile = pm.get_profile("user1")
        assert profile == {}

    def test_update_mood(self, pm):
        pm.update_profile("user1", mood="happy", cause="시험 끝남")
        profile = pm.get_profile("user1")
        assert len(profile["mood_history"]) == 1
        assert profile["mood_history"][0]["mood"] == "happy"

    def test_mood_history_limit(self, pm):
        for i in range(25):
            pm.update_profile("user1", mood=f"mood_{i}")
        profile = pm.get_profile("user1")
        assert len(profile["mood_history"]) == 20  # 최근 20개만 유지

    def test_update_genres(self, pm):
        pm.update_profile("user1", preferred_genres=["pop", "rock"])
        profile = pm.get_profile("user1")
        genres = profile["music_preferences"]["preferred_genres"]
        assert "pop" in genres
        assert "rock" in genres

    def test_genre_deduplication(self, pm):
        pm.update_profile("user1", preferred_genres=["pop"])
        pm.update_profile("user1", preferred_genres=["pop", "rock"])
        profile = pm.get_profile("user1")
        genres = profile["music_preferences"]["preferred_genres"]
        assert genres.count("pop") == 1

    def test_liked_tracks(self, pm):
        pm.update_profile("user1", liked_track="Happy Song")
        pm.update_profile("user1", liked_track="Sad Ballad")
        profile = pm.get_profile("user1")
        liked = profile["music_preferences"]["liked_tracks"]
        assert "Happy Song" in liked
        assert "Sad Ballad" in liked

    def test_liked_track_no_duplicates(self, pm):
        pm.update_profile("user1", liked_track="Happy Song")
        pm.update_profile("user1", liked_track="Happy Song")
        profile = pm.get_profile("user1")
        liked = profile["music_preferences"]["liked_tracks"]
        assert liked.count("Happy Song") == 1

    def test_care_notes(self, pm):
        pm.update_profile("user1", care_note="주로 저녁에 우울 추천 요청")
        profile = pm.get_profile("user1")
        assert "care_notes" in profile
        assert "주로 저녁에 우울 추천 요청" in profile["care_notes"]

    def test_care_notes_max_20(self, pm):
        for i in range(25):
            pm.update_profile("user1", care_note=f"노트 {i}")
        profile = pm.get_profile("user1")
        assert len(profile["care_notes"]) == 20
        # 마지막 20개만 유지 확인
        assert "노트 24" in profile["care_notes"]
        assert "노트 0" not in profile["care_notes"]

    def test_recommendations_acoustic_tendency(self, pm):
        recs = [
            {"genre": "pop", "acousticness": 0.8},
            {"genre": "rock", "acousticness": 0.6},
        ]
        pm.update_profile("user1", recommendations=recs)
        profile = pm.get_profile("user1")
        tendency = profile["music_preferences"]["acoustic_tendency"]
        assert abs(tendency - 0.7) < 0.001

    def test_recommendations_preferred_genres(self, pm):
        recs = [
            {"genre": "pop", "acousticness": 0.8},
            {"genre": "rock", "acousticness": 0.6},
        ]
        pm.update_profile("user1", recommendations=recs)
        profile = pm.get_profile("user1")
        genres = profile["music_preferences"]["preferred_genres"]
        assert "pop" in genres
        assert "rock" in genres
