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

        max_retries = 3
        thinking_content = ""
        for attempt in range(max_retries):
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
                # 2번째 재시도부터: thinking 내용이 있으면 "바로 응답해" 프롬프트 추가
                if attempt >= 1 and thinking_content:
                    messages.append({"role": "assistant", "content": thinking_content})
                    messages.append({"role": "user", "content": "위 분석을 바탕으로 사용자에게 보낼 따뜻한 추천 메시지를 한국어로 바로 작성해주세요. <think> 태그 없이 바로 응답하세요."})
                elif attempt >= 1:
                    messages.append({"role": "user", "content": "응답이 비어있었어요. <think> 태그 없이 바로 한국어 추천 메시지를 작성해주세요."})

                response = self.client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=messages,
                    temperature=0.7 + (attempt * 0.1)
                )
                msg = response.choices[0].message
                raw_content = msg.content
                # Qwen 등 일부 모델은 thinking을 별도 필드로 분리
                reasoning = getattr(msg, 'reasoning_content', None) or getattr(msg, 'reasoning', None)
                print(f"[Care] LLM raw (시도 {attempt+1}, content_len={len(raw_content) if raw_content else 0}, "
                      f"reasoning_len={len(reasoning) if reasoning else 0}, "
                      f"finish={response.choices[0].finish_reason}): "
                      f"content={repr((raw_content or '')[:150])}, "
                      f"reasoning={repr((reasoning or '')[:150])}", flush=True)
                # reasoning_content는 내부 사고 과정이므로 응답으로 사용하지 않음
                if not raw_content and reasoning:
                    print(f"[Care] ⚠️ content 비어있고 reasoning만 있음 (finish={response.choices[0].finish_reason}) → max_tokens 부족 가능성", flush=True)
                content = raw_content or ""

                # <think> 태그 처리
                if "<think>" in content:
                    # thinking 내용 보존 (재시도 시 활용)
                    think_part = content.split("</think>")[0].replace("<think>", "").strip()
                    if think_part and not thinking_content:
                        thinking_content = think_part
                        print(f"[Care] 💭 thinking 캡처 ({len(think_part)}자)", flush=True)
                    content = content.split("</think>")[-1].strip()

                # 빈 응답이면 재시도
                if not content.strip():
                    print(f"[Care] ⚠️ 빈 응답 (시도 {attempt+1}/{max_retries})", flush=True)
                    continue

                # 출력 가드레일
                content = validate_response(content)
                print(f"[Care] ✅ 응답 생성 성공 (시도 {attempt+1}, {len(content)}자)", flush=True)
                return content
            except Exception as e:
                print(f"[Care] ❌ 오류 (시도 {attempt+1}/{max_retries}): {str(e)[:120]}", flush=True)
                continue

        # 모든 재시도 실패 → thinking 내용이라도 반환
        if thinking_content:
            print(f"[Care] ⚠️ 전체 실패 → thinking 내용({len(thinking_content)}자)을 응답으로 사용", flush=True)
            return validate_response(thinking_content)
        return ""

    def run_stream(self, music_result: dict, gate_result: dict, user_message: str = "", history: str = ""):
        """Streaming 버전: 토큰을 yield하며 실시간 출력"""
        intent = gate_result.get("intent", "emotion")
        system_prompt = build_care_prompt(intent, history)
        user_content = self._format_music_result(music_result, intent, user_message)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            stream = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=0.7,
                stream=True
            )
            in_think = False
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                text = delta.content or ""
                # <think> 태그 필터링
                if "<think>" in text:
                    in_think = True
                    text = text.split("<think>")[0]
                if "</think>" in text:
                    in_think = False
                    text = text.split("</think>")[-1]
                if in_think:
                    continue
                if text:
                    yield text
            print("[Care] ✅ streaming 완료", flush=True)
        except Exception as e:
            print(f"[Care] ❌ streaming 오류: {str(e)[:120]}", flush=True)
            # 폴백: 기존 non-streaming 호출
            result = self.run(music_result, gate_result, user_message, history)
            if result:
                yield result

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
                        f"- {r['track_name']} by {r['track_artist']} "
                        f"(장르: {r.get('genre','')}, valence: {r.get('valence','')}, energy: {r.get('energy','')}, "
                        f"danceability: {r.get('danceability','')}, tempo: {r.get('tempo','')}, "
                        f"acousticness: {r.get('acousticness','')}, instrumentalness: {r.get('instrumentalness','')}, "
                        f"speechiness: {r.get('speechiness','')}, loudness: {r.get('loudness','')}, "
                        f"liveness: {r.get('liveness','')}, "
                        f"이유: {r.get('reason','')})"
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
        else:
            parts.append("Music Agent 응답: (없음)")

        result = "\n\n".join(parts)
        print(f"[Care] 입력 구성 완료 (len={len(result)}): {result[:300]}...", flush=True)
        return result
