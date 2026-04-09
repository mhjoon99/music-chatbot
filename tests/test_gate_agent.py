"""app/agents/gate_agent.py 단위 테스트 (LLM 호출은 mock)"""
import json
import pytest
from unittest.mock import patch, MagicMock
from app.agents.gate_agent import GateAgent, _keyword_classify


# ── _keyword_classify (순수 함수, mock 불필요) ─────────────────────────

class TestKeywordClassify:
    @pytest.mark.parametrize("text,expected", [
        ("Coldplay Yellow 같은 분위기 곡 추천해줘", "similar"),
        ("Adele의 Someone Like You 비슷한 곡", "similar"),
        ("BTS Dynamite 같은 에너지의 곡", "similar"),
        ("이 곡이랑 비슷한 느낌의 곡", "similar"),
    ])
    def test_similar_detection(self, text, expected):
        assert _keyword_classify(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("카페에서 듣기 좋은 곡", "situation"),
        ("러닝할 때 들을 음악", "situation"),
        ("새벽에 코딩하면서 들을 곡", "situation"),
        ("비 오는 날 듣기 좋은 BGM", "situation"),
        ("공부할 때 집중되는 음악", "situation"),
        ("드라이브하면서 들을 노래", "situation"),
    ])
    def test_situation_detection(self, text, expected):
        assert _keyword_classify(text) == expected

    @pytest.mark.parametrize("text", [
        "기분이 좋아",
        "우울해",
        "신나는 곡 추천해줘",
        "화나는 노래 틀어줘",
    ])
    def test_emotion_falls_through(self, text):
        # emotion은 키워드 규칙에 없음 → None 반환 → LLM에 위임
        assert _keyword_classify(text) is None


# ── GateAgent.run (LLM mock) ─────────────────────────────────────────

class TestGateAgentRun:
    @pytest.fixture
    def gate(self):
        with patch("app.agents.gate_agent.OpenAI"):
            agent = GateAgent()
        return agent

    @pytest.mark.parametrize("text", [
        "죽고 싶어... 너무 힘들어",
        "자살을 생각하고 있어",
        "자해를 했어",
        "목숨을 끊고 싶어",
        "끝내고 싶어 이제",
        "살고 싶지 않아",
        "죽을 것 같아",
        "생을 마감하고 싶어",
        "극단적인 선택을 하고 싶어",
    ])
    def test_danger_detected_returns_danger_flag(self, gate, text):
        result = gate.run(text)
        assert result["safety_flag"] == "danger"
        assert result["intent"] == "emotion"

    def test_keyword_similar_skips_llm(self, gate):
        result = gate.run("Coldplay Yellow 같은 분위기의 곡 추천해줘")
        assert result["intent"] == "similar"
        assert result["safety_flag"] == "safe"

    def test_keyword_situation_skips_llm(self, gate):
        result = gate.run("카페에서 책 읽을 때 들을 곡 추천해줘")
        assert result["intent"] == "situation"
        assert result["safety_flag"] == "safe"

    def test_llm_classification(self, gate):
        # LLM 응답 mock
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "intent": "emotion", "safety_flag": "safe", "complexity": "medium"
        })
        gate.client.chat.completions.create = MagicMock(return_value=mock_response)

        result = gate.run("기분이 너무 좋아")
        assert result["intent"] == "emotion"
        assert result["safety_flag"] == "safe"
        assert result["complexity"] == "medium"

    def test_off_topic_returns_off_topic_flag(self, gate):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "intent": "emotion", "safety_flag": "off_topic", "complexity": "low"
        })
        gate.client.chat.completions.create = MagicMock(return_value=mock_response)

        result = gate.run("오늘 날씨 어때?")
        assert result["safety_flag"] == "off_topic"

    def test_llm_json_parse_failure_falls_back_to_chaining(self, gate):
        # LLM이 잘못된 JSON 반환
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "not json"
        gate.client.chat.completions.create = MagicMock(return_value=mock_response)

        # _chaining_fallback도 mock (LLM 두 번 호출)
        with patch.object(gate, "_chaining_fallback", return_value={
            "intent": "emotion", "safety_flag": "safe", "complexity": "medium"
        }) as mock_chain:
            result = gate.run("기분이 좋아")
            mock_chain.assert_called_once()
            assert result["intent"] == "emotion"

    def test_think_tag_stripped(self, gate):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '<think>reasoning</think>{"intent":"emotion","safety_flag":"safe","complexity":"low"}'
        gate.client.chat.completions.create = MagicMock(return_value=mock_response)

        result = gate.run("기분이 좋아")
        assert result["intent"] == "emotion"
