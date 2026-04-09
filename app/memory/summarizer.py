from openai import OpenAI
from app.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

SUMMARY_PROMPT = """다음 대화 내용을 3줄 이내로 요약해주세요.
사용자의 감정 상태, 요청한 음악 유형, 추천 결과 만족도를 중심으로 요약합니다.
요약만 출력하세요."""

class Summarizer:
    def __init__(self):
        self.client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    def summarize(self, messages: list) -> str:
        """대화 메시지 리스트를 요약"""
        conversation_text = "\n".join([
            f"{'사용자' if m['role'] == 'user' else '에이전트'}: {m['content'][:200]}"
            for m in messages
        ])

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": conversation_text}
                ],
                temperature=0.7,
                max_tokens=200
            )
            content = response.choices[0].message.content or ""
            if "<think>" in content:
                content = content.split("</think>")[-1].strip()
            return content
        except Exception:
            return "요약 생성 실패"
