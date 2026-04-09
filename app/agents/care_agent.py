import json
from openai import OpenAI
from app.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
from app.prompts.care_prompt import build_care_prompt
from app.guardrails.output_validator import validate_response

class CareAgent:
    def __init__(self):
        self.client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    def run(self, music_result: dict, gate_result: dict, user_message: str = "", history: str = "") -> str:
        """Music Agent 결과를 바탕으로 공감적 추천 메시지 생성"""
        intent = gate_result.get("intent", "emotion")
        system_prompt = build_care_prompt(intent, history)

        # Music Agent 결과를 유저 메시지로 구성
        user_content = self._format_music_result(music_result, intent, user_message)

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            content = response.choices[0].message.content or ""
            # <think> 태그 제거
            if "<think>" in content:
                content = content.split("</think>")[-1].strip()

            # 출력 가드레일
            content = validate_response(content)
            return content
        except Exception as e:
            return f"추천 메시지 생성 중 오류가 발생했습니다. Music Agent가 찾은 곡 정보를 직접 확인해주세요."

    def _format_music_result(self, music_result: dict, intent: str, user_message: str = "") -> str:
        """Music Agent 결과를 Care Agent 입력 형식으로 변환 (간결하게)"""
        parts = [f"Intent: {intent}"]
        if user_message:
            parts.append(f"사용자 원본 메시지: {user_message}")

        response = music_result.get("final_response", "")
        if response:
            # JSON 응답이면 곡 목록만 추출하여 간결하게 전달
            try:
                data = json.loads(response)
                recs = data.get("recommendations", [])
                if recs:
                    songs = "\n".join([
                        f"- {r['track_name']} by {r['track_artist']} (장르: {r.get('genre','')}, valence: {r.get('valence','')}, energy: {r.get('energy','')}, 이유: {r.get('reason','')})"
                        for r in recs[:5]
                    ])
                    parts.append(f"추천 곡 목록:\n{songs}")
                    if data.get("iso_applied"):
                        parts.append(f"동질 원리 적용: {data.get('iso_direction', '')}")
                    if data.get("analysis"):
                        parts.append(f"분석: {data['analysis']}")
                else:
                    parts.append(f"Music Agent 응답:\n{response[:500]}")
            except (json.JSONDecodeError, TypeError):
                parts.append(f"Music Agent 응답:\n{response[:500]}")

        return "\n\n".join(parts)
