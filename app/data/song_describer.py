import json
import asyncio
import aiohttp
from pathlib import Path
from app.config import LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, DESCRIPTIONS_CACHE_PATH
from app.prompts.description_prompt import build_description_prompt

class SongDescriber:
    """적응형 Rate Limit + 배치 문장화 처리"""

    def __init__(self):
        self.concurrency = 5
        self.max_concurrency = 20
        self.error_count = 0
        self.checkpoint_interval = 100
        self.cache_path = Path(DESCRIPTIONS_CACHE_PATH)
        self.fallback_songs: list[str] = []

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_cache(self, results: dict):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    async def process_all(self, df) -> dict:
        """전체 곡 비동기 배치 처리"""
        results = self._load_cache()
        remaining = [(idx, row) for idx, row in df.iterrows()
                     if str(row["track_id"]) not in results]

        if not remaining:
            return results

        semaphore = asyncio.Semaphore(self.concurrency)
        total_remaining = len(remaining)
        processed = 0

        print(f"[SongDescriber] 총 {total_remaining}곡 처리 시작 (동시성: {self.concurrency})", flush=True)

        async with aiohttp.ClientSession() as session:
            batch = []
            for i, (idx, row) in enumerate(remaining):
                batch.append(self._process_one(session, semaphore, row))

                if (i + 1) % self.checkpoint_interval == 0:
                    batch_results = await asyncio.gather(*batch)
                    for r in batch_results:
                        if r:
                            results[r["id"]] = r["description"]
                    processed += len(batch)
                    self._save_cache(results)
                    self._adjust_concurrency()
                    semaphore = asyncio.Semaphore(self.concurrency)
                    print(f"[SongDescriber] {processed}/{total_remaining} ({processed*100//total_remaining}%) 완료 | 동시성: {self.concurrency} | fallback: {len(self.fallback_songs)}곡", flush=True)
                    batch = []

            if batch:
                batch_results = await asyncio.gather(*batch)
                for r in batch_results:
                    if r:
                        results[r["id"]] = r["description"]
                processed += len(batch)
                self._save_cache(results)
                print(f"[SongDescriber] {processed}/{total_remaining} (100%) 완료 | fallback: {len(self.fallback_songs)}곡", flush=True)

        # 1차 실패 곡들에 대해 LLM 재시도 (retry pass)
        if self.fallback_songs:
            print(f"[SongDescriber] Retrying {len(self.fallback_songs)} failed songs via LLM...")
            retry_targets = [(idx, row) for idx, row in df.iterrows()
                             if str(row["track_id"]) in self.fallback_songs]
            retry_succeeded = []

            async with aiohttp.ClientSession() as session:
                retry_sem = asyncio.Semaphore(5)
                retry_batch = [self._process_one(session, retry_sem, row) for _, row in retry_targets]
                retry_results = await asyncio.gather(*retry_batch)
                for r in retry_results:
                    if r and r["id"] in self.fallback_songs:
                        # fallback이 아닌 LLM 결과인지 확인 (규칙 기반은 "은(는)" 패턴)
                        if "은(는)" not in r["description"] or len(r["description"]) > 100:
                            results[r["id"]] = r["description"]
                            retry_succeeded.append(r["id"])

            for sid in retry_succeeded:
                self.fallback_songs.remove(sid)

            if retry_succeeded:
                self._save_cache(results)
                print(f"[SongDescriber] Retry succeeded: {len(retry_succeeded)} songs recovered via LLM")

        total = len(remaining)
        fallback_count = len(self.fallback_songs)
        if fallback_count > 0:
            print(f"[SongDescriber] {fallback_count} songs still using rule-based fallback out of {total} total")
            for song_id in self.fallback_songs:
                print(f"  - fallback: {song_id}")
        else:
            print(f"[SongDescriber] All {total} songs described successfully via LLM")

        return results

    def _adjust_concurrency(self):
        if self.error_count == 0 and self.concurrency < self.max_concurrency:
            self.concurrency = min(self.concurrency + 5, self.max_concurrency)
        elif self.error_count > 10:
            self.concurrency = max(self.concurrency // 2, 3)
        self.error_count = 0

    async def _process_one(self, session, semaphore, row) -> dict | None:
        async with semaphore:
            prompt = build_description_prompt(row.to_dict())
            for attempt in range(3):
                try:
                    resp = await session.post(
                        f"{LLM_BASE_URL}/chat/completions",
                        json={
                            "model": LLM_MODEL,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.7,
                            "max_tokens": 200
                        },
                        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                        timeout=aiohttp.ClientTimeout(total=10)
                    )
                    if resp.status == 429:
                        self.error_count += 1
                        await asyncio.sleep(2 ** attempt)
                        continue
                    data = await resp.json()
                    desc = data["choices"][0]["message"]["content"]
                    if "<think>" in desc:
                        desc = desc.split("</think>")[-1].strip()
                    return {"id": str(row["track_id"]), "description": desc}
                except Exception:
                    self.error_count += 1
                    await asyncio.sleep(1)

            # 3회 실패 → 규칙 기반 fallback
            track_id = str(row["track_id"])
            self.fallback_songs.append(track_id)
            return {"id": track_id, "description": self._rule_based_fallback(row)}

    def _rule_based_fallback(self, row) -> str:
        from app.data.embedder import _map_feature, KEY_NAMES
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
        mode_val = float(row.get("mode", 0.5))
        mode_desc = "장조(밝은)" if mode_val >= 0.5 else "단조(어두운)"
        key_idx = round(float(row.get("key", 0)) * 11)
        key_desc = KEY_NAMES[min(key_idx, 11)]

        artist = row.get('track_artist', '')
        name = row.get('track_name', '')
        genre = row.get('playlist_genre', '')

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
