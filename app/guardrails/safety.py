import re

DANGER_KEYWORDS = [
    "죽고 싶", "자살", "자해", "목숨", "끝내고 싶", "살고 싶지 않",
    "죽을", "생을 마감", "극단적"
]

EMERGENCY_RESPONSE = """당신의 마음이 많이 힘드시군요.
전문적인 도움이 필요할 수 있어요.

🆘 정신건강 위기상담: 1577-0199 (24시간)
🆘 자살예방 상담전화: 1393 (24시간)

혼자 감당하지 않으셔도 돼요. 전문 상담사와 이야기해보세요."""

OFF_TOPIC_RESPONSE = """저는 음악 추천 에이전트 MindTune이에요! 🎵
기분이나 상황을 알려주시면 어울리는 음악을 찾아드릴게요.

예시:
- "오늘 좀 우울해, 위로가 되는 곡 추천해줘"
- "카페에서 책 읽을 때 들을 BGM 추천해줘"
- "Coldplay Yellow 같은 분위기의 곡 찾아줘" """

def check_danger(text: str) -> bool:
    """위험 신호 감지"""
    text_lower = text.lower()
    return any(kw in text_lower for kw in DANGER_KEYWORDS)
