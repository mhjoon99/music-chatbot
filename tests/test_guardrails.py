"""app/guardrails/ 모듈 단위 테스트"""
import pytest
from app.guardrails.safety import check_danger, DANGER_KEYWORDS, EMERGENCY_RESPONSE, OFF_TOPIC_RESPONSE
from app.guardrails.output_validator import validate_response, verify_tracks_in_db


# ── check_danger ──────────────────────────────────────────────────────

class TestCheckDanger:
    @pytest.mark.parametrize("text", [
        "죽고 싶어",
        "자살하고 싶다",
        "자해를 했어",
        "생을 마감하고 싶어",
        "극단적인 선택을 하고 싶어",
    ])
    def test_danger_detected(self, text):
        assert check_danger(text) is True

    @pytest.mark.parametrize("text", [
        "오늘 기분이 좋아",
        "신나는 노래 추천해줘",
        "비 오는 날 듣기 좋은 곡",
        "Coldplay Yellow 같은 곡",
        "",
    ])
    def test_safe_messages(self, text):
        assert check_danger(text) is False

    def test_emergency_response_has_hotline(self):
        assert "1577-0199" in EMERGENCY_RESPONSE
        assert "1393" in EMERGENCY_RESPONSE

    def test_off_topic_response_has_examples(self):
        assert "MindTune" in OFF_TOPIC_RESPONSE


# ── validate_response ─────────────────────────────────────────────────

class TestValidateResponse:
    def test_clean_response_unchanged(self):
        text = "이 곡은 우울한 기분에 잘 어울려요."
        assert validate_response(text) == text

    @pytest.mark.parametrize("phrase", [
        "치료합니다",
        "치료할 수 있",
        "진단",
        "장애가 있",
        "병이 있",
        "처방",
    ])
    def test_forbidden_phrase_replaced(self, phrase):
        text = f"이 음악은 우울증을 {phrase}."
        result = validate_response(text)
        assert phrase not in result
        assert "[부적절한 표현 제거됨]" in result


# ── verify_tracks_in_db ───────────────────────────────────────────────

class TestVerifyTracksInDb:
    def test_all_valid(self, sample_df):
        valid = verify_tracks_in_db(["tid_0", "tid_1", "tid_2"], sample_df)
        assert valid == ["tid_0", "tid_1", "tid_2"]

    def test_some_invalid(self, sample_df):
        valid = verify_tracks_in_db(["tid_0", "fake_id", "tid_1"], sample_df)
        assert valid == ["tid_0", "tid_1"]

    def test_all_invalid(self, sample_df):
        valid = verify_tracks_in_db(["fake_1", "fake_2"], sample_df)
        assert valid == []

    def test_empty_list(self, sample_df):
        valid = verify_tracks_in_db([], sample_df)
        assert valid == []
