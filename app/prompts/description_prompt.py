def build_description_prompt(row: dict) -> str:
    """CSV 행 데이터를 곡 설명 프롬프트로 변환"""
    return f"""다음 곡의 태그 정보를 바탕으로, 이 곡의 분위기와 특성을
2~3문장의 자연어 설명으로 작성해주세요.
곡명: {row.get('track_name', 'Unknown')} / 아티스트: {row.get('track_artist', 'Unknown')}
장르: {row.get('playlist_genre', '')} / 서브장르: {row.get('playlist_subgenre', '')}
에너지: {row.get('energy', 0)} / 긍정도: {row.get('valence', 0)} / 템포: {row.get('tempo', 0)}BPM
어쿠스틱: {row.get('acousticness', 0)} / 정신건강 라벨: {row.get('Mental_Health_Label', 'Normal')}"""
