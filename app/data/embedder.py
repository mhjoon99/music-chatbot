import json
import chromadb
from sentence_transformers import SentenceTransformer
from app.config import CHROMA_DB_PATH, EMBEDDING_MODEL, DESCRIPTIONS_CACHE_PATH

def load_descriptions(cache_path: str = None) -> dict:
    """문장화 캐시 로드"""
    path = cache_path or DESCRIPTIONS_CACHE_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def build_chroma_db(df, descriptions: dict, db_path: str = None, model_name: str = None):
    """전체 곡 임베딩 → ChromaDB 저장 (배치 임베딩으로 고속 처리)"""
    import sys
    db_path = db_path or CHROMA_DB_PATH
    model_name = model_name or EMBEDDING_MODEL

    print("[embedder] 모델 로딩 중...", flush=True)
    embedder = SentenceTransformer(model_name)
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection("mindtune_songs")

    # 이미 저장된 곡 확인
    existing = set()
    try:
        existing_count = collection.count()
        if existing_count > 0:
            existing_data = collection.get(include=[])
            if existing_data and existing_data["ids"]:
                existing = set(existing_data["ids"])
    except Exception:
        pass

    print(f"[embedder] 기존 임베딩: {len(existing)}곡, 전체: {len(df)}곡", flush=True)

    # 새로 임베딩할 곡 필터링
    new_rows = []
    for _, row in df.iterrows():
        track_id = str(row["track_id"])
        if track_id not in existing:
            new_rows.append(row)

    if not new_rows:
        print("[embedder] 모든 곡이 이미 임베딩되어 있습니다.", flush=True)
        return embedder, collection

    total = len(new_rows)
    print(f"[embedder] {total}곡 임베딩 시작...", flush=True)

    BATCH_SIZE = 512
    for batch_start in range(0, total, BATCH_SIZE):
        batch_rows = new_rows[batch_start:batch_start + BATCH_SIZE]

        # 설명 텍스트 준비
        docs = []
        metas = []
        ids = []
        for row in batch_rows:
            track_id = str(row["track_id"])
            description = descriptions.get(track_id, "")
            if not description:
                description = _rule_based_description(row)
            docs.append(description)
            metas.append({
                "track_id": track_id,
                "track_name": str(row.get("track_name", "")),
                "track_artist": str(row.get("track_artist", "")),
                "genre": str(row.get("playlist_genre", "")),
                "subgenre": str(row.get("playlist_subgenre", "")),
                "energy": float(row.get("energy", 0)),
                "valence": float(row.get("valence", 0)),
                "acousticness": float(row.get("acousticness", 0)),
                "danceability": float(row.get("danceability", 0)),
                "instrumentalness": float(row.get("instrumentalness", 0)),
                "speechiness": float(row.get("speechiness", 0)),
                "tempo": float(row.get("tempo", 0)),
                "loudness": float(row.get("loudness", 0)),
                "liveness": float(row.get("liveness", 0)),
                "mental_health": str(row.get("Mental_Health_Label", "Normal")),
                "popularity": int(row.get("track_popularity", 0))
            })
            ids.append(track_id)

        # 배치 임베딩 (한 번에 512개씩 — 개별 encode보다 ~10배 빠름)
        embeddings = embedder.encode(docs, show_progress_bar=False).tolist()

        # ChromaDB에 저장
        collection.add(documents=docs, embeddings=embeddings,
                      metadatas=metas, ids=ids)

        done = min(batch_start + BATCH_SIZE, total)
        pct = done / total * 100
        print(f"[embedder] {done}/{total} ({pct:.0f}%) 완료", flush=True)

    print(f"[embedder] 임베딩 완료! 총 {total}곡 저장됨", flush=True)
    return embedder, collection

def _map_feature(value, levels):
    """0~1 값을 5단계 텍스트로 매핑"""
    if value < 0.2: return levels[0]
    elif value < 0.4: return levels[1]
    elif value < 0.6: return levels[2]
    elif value < 0.8: return levels[3]
    else: return levels[4]

KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def _rule_based_description(row) -> str:
    """규칙 기반 fallback 설명 생성 — 11개 오디오 피처 + genre 포함"""
    energy_desc = _map_feature(float(row.get("energy", 0.5)),
        ["매우 차분하고 고요한", "차분한", "적당한 에너지의", "활기찬", "매우 활기차고 역동적인"])
    valence_desc = _map_feature(float(row.get("valence", 0.5)),
        ["매우 어둡고 우울한", "다소 우울한", "중립적인", "밝고 긍정적인", "매우 밝고 행복한"])
    dance_desc = _map_feature(float(row.get("danceability", 0.5)),
        ["춤추기 어려운", "약간의 리듬감이 있는", "적당히 리듬감 있는", "춤추기 좋은", "매우 댄서블한"])
    tempo_desc = _map_feature(float(row.get("tempo", 0.5)),
        ["매우 느린 템포의", "느린 템포의", "중간 템포의", "빠른 템포의", "매우 빠른 템포의"])
    acoustic_desc = _map_feature(float(row.get("acousticness", 0.5)),
        ["전자음 위주의", "약간 전자적인", "어쿠스틱과 전자음이 섞인", "어쿠스틱 느낌의", "매우 어쿠스틱한"])
    instrumental_desc = _map_feature(float(row.get("instrumentalness", 0.0)),
        ["보컬 중심의", "보컬이 많은", "보컬과 연주가 균형 잡힌", "연주 중심의", "순수 기악곡인"])
    speech_desc = _map_feature(float(row.get("speechiness", 0.1)),
        ["가사가 거의 없는", "가사가 적은", "보통 수준의 가사가 있는", "대사/랩이 많은", "대사/랩 위주의"])
    loud_desc = _map_feature(float(row.get("loudness", 0.5)),
        ["매우 부드러운 사운드의", "부드러운 사운드의", "보통 음량의", "강렬한 사운드의", "매우 강렬하고 파워풀한"])
    live_desc = _map_feature(float(row.get("liveness", 0.2)),
        ["스튜디오 녹음의", "약간의 스튜디오 느낌의", "적당한 라이브 느낌의", "라이브 느낌이 강한", "라이브 공연의"])

    # mode: 0=단조, 1=장조 (이진값)
    mode_val = float(row.get("mode", 0.5))
    mode_desc = "장조(밝은)" if mode_val >= 0.5 else "단조(어두운)"

    # key: 0~11 → 음이름 (MinMaxScaled 0~1이므로 역변환)
    key_val = float(row.get("key", 0))
    key_idx = round(key_val * 11)
    key_desc = KEY_NAMES[min(key_idx, 11)]

    genre = row.get("playlist_genre", "")
    artist = row.get("track_artist", "")
    name = row.get("track_name", "")

    numeric_prefix = (
        f"energy {round(float(row.get('energy', 0.5)), 2)}, "
        f"valence {round(float(row.get('valence', 0.5)), 2)}, "
        f"danceability {round(float(row.get('danceability', 0.5)), 2)}, "
        f"tempo {round(float(row.get('tempo', 0.5)), 2)}, "
        f"acousticness {round(float(row.get('acousticness', 0.5)), 2)}, "
        f"instrumentalness {round(float(row.get('instrumentalness', 0.0)), 2)}, "
        f"speechiness {round(float(row.get('speechiness', 0.1)), 2)}, "
        f"loudness {round(float(row.get('loudness', 0.5)), 2)}, "
        f"liveness {round(float(row.get('liveness', 0.2)), 2)}, "
        f"mode {int(round(mode_val))}, key {key_idx}. "
    )

    return (f"{artist}의 '{name}'은(는) {numeric_prefix}{energy_desc}, {valence_desc}, {dance_desc}, {tempo_desc}, "
            f"{acoustic_desc}, {instrumental_desc}, {speech_desc}, {loud_desc}, {live_desc}, "
            f"{mode_desc} {key_desc}키 {genre} 곡입니다.")
