import re
import json
from openai import OpenAI
from app.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
from app.prompts.gate_prompt import GATE_SYSTEM_PROMPT
from app.guardrails.safety import check_danger

# 키워드 규칙 기반 사전 분류 (LLM 보완)
SIMILAR_PATTERNS = [
    r"(?:Coldplay|Adele|BTS|Ed Sheeran|Billie Eilish|The Weeknd|Eminem|Norah Jones)",
    r"(?:Yellow|Dynamite|Shape of You|Blinding Lights|Someone Like You|bad guy)",
    r"같은\s*(?:분위기|느낌|곡|스타일|에너지)",
    r"비슷한\s*(?:곡|노래|음악|느낌)",
    r"느낌의\s*(?:곡|노래|음악)",
    r"스타일.{0,5}(?:곡|노래|추천)",
    r"(?:이 곡|저 곡|그 노래).{0,10}(?:비슷|같은)",
]

SITUATION_PATTERNS = [
    r"(?:카페|헬스장|사무실|도서관|집|차 안|비행기)",
    r"(?:코딩|운동|러닝|공부|독서|드라이브|요가|파티|수면|잠자|산책)",
    r"(?:새벽|아침|저녁|밤|비 오는|비오는|일요일|주말)",
    r"(?:할 때|하면서|할 건데|하는데|하고 있)",
    r"(?:배경.*음악|BGM|분위기.*곡|집중.*곡|잠.*들|자기 전)",
]

def _keyword_classify(text: str) -> str | None:
    """키워드 규칙 기반 사전 분류. 매칭되면 intent 반환, 아니면 None."""
    for pattern in SIMILAR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "similar"
    for pattern in SITUATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "situation"
    return None


class GateAgent:
    def __init__(self):
        self.client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    def run(self, user_message: str) -> dict:
        """사용자 메시지 분류 + 안전 체크"""
        # 코드 레벨 위험 신호 사전 체크
        if check_danger(user_message):
            return {"intent": "emotion", "safety_flag": "danger", "complexity": "low"}

        # 키워드 규칙 기반 사전 분류 (LLM 보완)
        keyword_intent = _keyword_classify(user_message)

        # 최적화: 키워드로 확실히 분류되면 LLM 호출 건너뛰기
        if keyword_intent:
            print(f"[Gate] 키워드 분류 → {keyword_intent} (LLM 호출 생략)", flush=True)
            return {"intent": keyword_intent, "safety_flag": "safe", "complexity": "medium"}

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": GATE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=100
            )
            content = (response.choices[0].message.content or "").strip()
            # JSON 파싱
            # <think> 태그가 있으면 제거
            if "<think>" in content:
                content = content.split("</think>")[-1].strip()

            result = json.loads(content)
            # 필수 필드 검증
            assert "intent" in result
            assert "safety_flag" in result
            # 키워드 규칙이 LLM과 다르면 키워드 우선 (4B 모델 보완)
            if keyword_intent and result["intent"] != keyword_intent:
                print(f"[Gate] 키워드 보정: LLM={result['intent']} → 키워드={keyword_intent}", flush=True)
                result["intent"] = keyword_intent
            return result
        except (json.JSONDecodeError, AssertionError):
            # Fallback: 키워드 분류 결과가 있으면 바로 사용
            if keyword_intent:
                print(f"[Gate] JSON 파싱 실패 → 키워드 분류 사용: {keyword_intent}", flush=True)
                return {"intent": keyword_intent, "safety_flag": "safe", "complexity": "medium"}
            # 그 외: Chaining
            return self._chaining_fallback(user_message)

    def _chaining_fallback(self, user_message: str) -> dict:
        """JSON 파싱 실패 시 단계별 체이닝 폴백"""
        result = {"intent": "emotion", "safety_flag": "safe", "complexity": "medium"}

        try:
            # Chain 1: Intent 분류
            resp1 = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": "다음 메시지의 intent를 emotion/situation/similar 중 하나로만 답하세요. 다른 텍스트 없이 단어 하나만 출력하세요."},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3, max_tokens=10
            )
            intent_text = resp1.choices[0].message.content.strip().lower()
            if "<think>" in intent_text:
                intent_text = intent_text.split("</think>")[-1].strip()
            if intent_text in ["emotion", "situation", "similar"]:
                result["intent"] = intent_text
        except Exception:
            pass

        try:
            # Chain 2: Safety 체크
            resp2 = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": "다음 메시지에 자해/자살/위험 신호가 있으면 danger, 음악과 무관하면 off_topic, 그 외에는 safe로만 답하세요. 단어 하나만 출력하세요."},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3, max_tokens=10
            )
            safety_text = resp2.choices[0].message.content.strip().lower()
            if "<think>" in safety_text:
                safety_text = safety_text.split("</think>")[-1].strip()
            if safety_text in ["danger", "off_topic", "safe"]:
                result["safety_flag"] = safety_text
        except Exception:
            pass

        return result
