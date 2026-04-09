import chromadb
import numpy as np
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
from app.config import CHROMA_DB_PATH, EMBEDDING_MODEL

# 싱글톤 패턴으로 임베더와 컬렉션 재사용
_embedder = None
_collection = None
_bm25_cache = {}

def _get_embedder():
    """임베더 싱글톤 반환"""
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder

def _get_collection():
    """ChromaDB 컬렉션 싱글톤 반환"""
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _collection = client.get_or_create_collection("mindtune_songs")
    return _collection

def _get_or_build_bm25(collection):
    """BM25 인덱스 빌드 (캐시, 최초 1회)"""
    if "index" not in _bm25_cache:
        all_docs = collection.get(include=["documents", "metadatas"])
        corpus = [doc.split() for doc in all_docs["documents"]]
        _bm25_cache["index"] = BM25Okapi(corpus)
        _bm25_cache["ids"] = all_docs["ids"]
        _bm25_cache["metadatas"] = all_docs["metadatas"]
    return _bm25_cache["index"], _bm25_cache["ids"], _bm25_cache["metadatas"]

def search_by_description(query: str, genre_filter: list = None, top_k: int = 20) -> dict:
    """자연어 설명으로 의미적 유사곡 하이브리드 검색 (벡터 + BM25)"""
    collection = _get_collection()
    if collection is None:
        return {"tracks": [], "count": 0}

    candidate_k = top_k * 2

    # 벡터 검색 (ChromaDB)
    if genre_filter:
        where = {"$or": [{"genre": {"$in": genre_filter}}, {"subgenre": {"$in": genre_filter}}]}
    else:
        where = None
    vec_results = collection.query(
        query_texts=[query], n_results=candidate_k, where=where,
        include=["documents", "metadatas", "distances", "ids"]
    )

    # 벡터 결과 맵 구성: {id: (similarity, metadata)}
    vec_score_map = {}
    vec_meta_map = {}
    if vec_results and vec_results["ids"] and vec_results["ids"][0]:
        for doc_id, dist, meta in zip(
            vec_results["ids"][0],
            vec_results["distances"][0],
            vec_results["metadatas"][0]
        ):
            vec_score_map[doc_id] = float(1 - dist)
            vec_meta_map[doc_id] = meta

    # BM25 검색
    bm25, all_ids, all_metadatas = _get_or_build_bm25(collection)
    bm25_scores = bm25.get_scores(query.split())

    # BM25 상위 candidate_k 결과 맵 구성
    top_bm25_indices = np.argsort(bm25_scores)[::-1][:candidate_k]
    bm25_score_map = {}
    bm25_meta_map = {}
    for idx in top_bm25_indices:
        doc_id = all_ids[idx]
        bm25_score_map[doc_id] = float(bm25_scores[idx])
        bm25_meta_map[doc_id] = all_metadatas[idx]

    # 후보 합집합
    all_candidate_ids = set(vec_score_map.keys()) | set(bm25_score_map.keys())

    # 장르 필터 적용 (BM25 후보에도 적용)
    if genre_filter:
        filtered_ids = set()
        for cid in all_candidate_ids:
            meta = vec_meta_map.get(cid) or bm25_meta_map.get(cid, {})
            if meta.get("genre") in genre_filter or meta.get("subgenre") in genre_filter:
                filtered_ids.add(cid)
        all_candidate_ids = filtered_ids

    if not all_candidate_ids:
        return {"tracks": [], "count": 0}

    # 점수 정규화 (0-1)
    vec_vals = np.array([vec_score_map.get(cid, 0.0) for cid in all_candidate_ids])
    bm25_vals = np.array([bm25_score_map.get(cid, 0.0) for cid in all_candidate_ids])

    vec_min, vec_max = vec_vals.min(), vec_vals.max()
    bm25_min, bm25_max = bm25_vals.min(), bm25_vals.max()

    vec_norm = (vec_vals - vec_min) / (vec_max - vec_min + 1e-9)
    bm25_norm = (bm25_vals - bm25_min) / (bm25_max - bm25_min + 1e-9)

    final_scores = 0.6 * vec_norm + 0.4 * bm25_norm

    # 최종 랭킹
    scored_candidates = sorted(
        zip(final_scores, all_candidate_ids),
        key=lambda x: x[0],
        reverse=True
    )

    tracks = []
    for final_score, cid in scored_candidates[:top_k]:
        meta = vec_meta_map.get(cid) or bm25_meta_map.get(cid, {})
        tracks.append({
            "track_id": meta.get("track_id", ""),
            "track_name": meta.get("track_name", ""),
            "track_artist": meta.get("track_artist", ""),
            "genre": meta.get("subgenre", "") or meta.get("genre", ""),
            "valence": meta.get("valence", 0),
            "energy": meta.get("energy", 0),
            "similarity": float(final_score),
            "mental_health": meta.get("mental_health", "Normal")
        })

    return {"tracks": tracks, "count": len(tracks)}
