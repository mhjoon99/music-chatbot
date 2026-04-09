# MindTune - AI 기반 음악 심리 케어 챗봇

MindTune은 사용자의 감정과 상황을 이해하여 맞춤형 음악을 추천하는 AI 챗봇입니다. 3개의 전문 에이전트(Gate, Music, Care)가 협력하여 공감적인 음악 추천 경험을 제공하며, 음악치료의 동질 원리(ISO Principle)를 적용하여 감정 변화를 유도하는 플레이리스트를 구성합니다.

## 기술 스택

| 영역 | 기술 |
|------|------|
| **프론트엔드** | Streamlit |
| **LLM** | OpenAI-compatible API (LLM_BASE_URL 설정) |
| **벡터 검색** | ChromaDB + sentence-transformers (all-MiniLM-L6-v2) |
| **음악 메타데이터** | Spotify Web API (spotipy) |
| **데이터 처리** | pandas, scikit-learn (MinMaxScaler, cosine_similarity) |
| **데이터베이스** | SQLite (대화 영속성) |
| **시각화** | Plotly (감정 변화 산점도) |
| **컨테이너** | Docker, Docker Compose |
| **언어** | Python 3.11+ |

## 실행 방법

### 사전 준비

1. `.env.example`을 복사하여 `.env` 파일을 생성합니다:

```bash
cp .env.example .env
```

2. `.env` 파일에 필수 환경변수를 설정합니다:

```env
# 필수: LLM 설정
LLM_BASE_URL=http://your-llm-server:port/v1
LLM_API_KEY=your-api-key-here
LLM_MODEL=your-model-name

# 선택: Spotify (미설정 시 YouTube 폴백)
SPOTIFY_CLIENT_ID=your-spotify-client-id
SPOTIFY_CLIENT_SECRET=your-spotify-client-secret

# 데이터 경로 (기본값 사용 가능)
DATA_PATH=data/Music_recommendation.csv
CHROMA_DB_PATH=data/chroma_db
SQLITE_DB_PATH=data/mindtune.db
EMBEDDING_MODEL=all-MiniLM-L6-v2
MAX_REACT_ITERATIONS=5
```

3. `data/` 디렉토리에 `Music_recommendation.csv` 데이터셋을 배치합니다.

### 로컬 실행

```bash
# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 실행
streamlit run streamlit_app.py
```

브라우저에서 `http://localhost:8501`로 접속합니다.

### Docker 실행

```bash
# 빌드 및 실행
docker compose up --build

# 백그라운드 실행
docker compose up -d --build
```

- 포트: `8501`
- 헬스체크: `http://localhost:8501/_stcore/health`
- 데이터 볼륨: `./data:/app/data` (영속성 보장)
- HuggingFace 캐시: Docker 볼륨으로 관리 (재빌드 시 모델 재다운로드 방지)

## 핵심 기능

### 3가지 추천 모드

| 모드 | 사용 예시 | 처리 방식 |
|------|-----------|-----------|
| **감정 기반** (emotion) | "오늘 좀 우울해" | 감정 키워드 → 오디오 피처 매핑 → 동질 원리 플레이리스트 |
| **상황 기반** (situation) | "카페에서 책 읽을 때 BGM" | 상황 프리셋 → 피처+벡터 검색 → 리랭킹 |
| **유사곡 탐색** (similar) | "Coldplay Yellow 같은 곡" | 참조곡 조회 → 벡터 유사도 중심 검색 → 리랭킹 |

### 동질 원리 (ISO Principle)

음악치료에서 사용하는 동질 원리를 적용합니다. 사용자의 현재 감정(valence)에서 목표 감정까지 점진적으로 변화하는 플레이리스트를 구성하여 자연스러운 감정 이동을 유도합니다.

### Spotify 연동

- 추천 곡의 Spotify 임베드 플레이어 제공
- 앨범 아트 표시
- Spotify에서 찾을 수 없는 곡은 YouTube 검색으로 폴백
- 대기 중 데이터셋 서브장르 기반 트렌딩 곡 표시

### 감정 변화 시각화

사이드바에 사용자의 턴별 감정 상태(긍정도/에너지)를 산점도로 시각화합니다. 키워드 기반으로 추정하며 LLM 호출 없이 처리합니다.

### 피드백 버튼

추천 결과에 대해 "더 신나게", "더 차분하게", "다른 장르" 버튼으로 즉각적인 재추천을 요청할 수 있습니다.

## 시스템 아키텍처

```
사용자 입력
    │
    ▼
┌─────────────────┐
│   Gate Agent     │  의도 분류 (emotion/situation/similar)
│                  │  안전 체크 (danger/off_topic/safe)
│                  │  키워드 규칙 → LLM 폴백 → 체이닝 폴백
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Music Agent     │  ReAct 루프 (최대 7회 반복)
│                  │  6개 도구 자율 선택 및 실행
│                  │  Tool-Calling 기반 (OpenAI Function Calling)
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼          (병렬 실행)
┌────────┐ ┌──────────┐
│  Care  │ │ Spotify  │
│ Agent  │ │  검색    │
└───┬────┘ └────┬─────┘
    │           │
    ▼           ▼
┌─────────────────┐
│  최종 응답 조합   │  공감 메시지 + Spotify 메타데이터 병합
│  + 출력 가드레일  │
└─────────────────┘
```

## 에이전트 구조

### Gate Agent (`app/agents/gate_agent.py`)

사용자 메시지를 분류하고 안전성을 검사합니다.

- **위험 신호 감지**: 자해/자살 관련 키워드 사전 체크 → 즉시 긴급 응답 (위기상담 전화번호 안내)
- **키워드 규칙 분류**: 정규식 패턴으로 similar/situation 사전 분류 (LLM 호출 생략으로 지연 최소화)
- **LLM 분류**: 키워드로 판별 불가 시 LLM JSON 분류
- **체이닝 폴백**: JSON 파싱 실패 시 단계별 체이닝 (Intent → Safety 순차 호출)

### Music Agent (`app/agents/music_agent.py`)

ReAct 패턴으로 도구를 자율 선택하며 음악을 검색합니다.

**사용 가능한 도구 (6개):**

| 도구 | 설명 |
|------|------|
| `search_by_features` | 오디오 피처 범위 필터링 + 코사인 유사도 랭킹 |
| `search_by_description` | ChromaDB 벡터 검색 (자연어 쿼리) |
| `lookup_song` | 특정 곡 상세 정보 조회 |
| `get_mental_health_songs` | Mental Health Label 기반 필터링 |
| `rerank_results` | 다중 기준 융합 리랭킹 |
| `build_iso_playlist` | 동질 원리 기반 곡 순서 배열 |

**슬라이딩 윈도우**: 컨텍스트 관리를 위해 system + user + 최근 8개 도구 교환 메시지만 유지합니다.

**폴백 전략**: LLM 응답이 부족하거나 max_iterations 도달 시, 수집된 rerank/iso 결과로 직접 JSON 응답을 구성합니다.

### Care Agent (`app/agents/care_agent.py`)

Music Agent의 추천 결과를 바탕으로 공감적인 자연어 응답을 생성합니다. 출력 가드레일을 통해 의료적 표현(치료, 진단, 처방 등)을 필터링합니다.

## RAG 구조

### 데이터 전처리 (`app/data/loader.py`)

1. CSV 로드 → `track_id` 중복 제거 → `track_name + track_artist` 중복 제거
2. 빈 `track_name` 행 제거, `Mental_Health_Label` null → "Normal" 매핑
3. 오디오 피처 9종 MinMaxScaler 정규화 (0~1)
4. `tempo_norm` 컬럼 생성 (정규화된 템포)

### 임베딩 및 벡터 DB (`app/data/embedder.py`)

1. **문장화**: 곡 설명 캐시(`song_descriptions.json`) 로드, 없으면 규칙 기반 설명 자동 생성
2. **배치 임베딩**: sentence-transformers로 512개씩 배치 인코딩 (개별 대비 ~10배 빠름)
3. **ChromaDB 저장**: 영구 저장소(`data/chroma_db/`)에 임베딩 + 메타데이터 저장
4. **증분 처리**: 이미 임베딩된 곡은 건너뜀

### 검색 및 랭킹

**피처 기반 검색** (`app/tools/search_by_features.py`):
- 오디오 피처 범위 필터링 (valence, energy, tempo, danceability, acousticness 등)
- 필터링 결과에 대해 타겟 벡터와의 코사인 유사도 랭킹

**벡터 검색** (`app/tools/search_by_description.py`):
- ChromaDB 쿼리 (자연어 → 임베딩 → 유사도 검색)
- 선택적 장르 필터링

**다중 기준 리랭킹** (`app/tools/reranker.py`):

| Intent | 벡터 유사도 | 피처 유사도 | 인기도 |
|--------|------------|------------|--------|
| emotion | 30% | **60%** | 10% |
| situation | 40% | **50%** | 10% |
| similar | **50%** | 40% | 10% |

- "유명", "인기" 등 키워드 감지 시 인기도 가중치 동적 상향 (10% → 40%)

## 안전장치 (Guardrails)

### 입력 안전 체크 (`app/guardrails/safety.py`)

- **위험 키워드 감지**: "죽고 싶", "자살", "자해" 등 9개 키워드 매칭
- **긴급 응답**: 정신건강 위기상담(1577-0199), 자살예방 상담전화(1393) 24시간 연결 안내
- **범위 외 필터링**: 음악과 무관한 질문은 안내 메시지로 응답

### 출력 검증 (`app/guardrails/output_validator.py`)

- **금지 표현 필터링**: "치료합니다", "진단", "처방" 등 의료적 표현 자동 제거
- **DB 존재 검증**: 추천 곡이 실제 데이터셋에 존재하는지 확인 (할루시네이션 방지)

## 메모리 & 프로필

### 대화 영속성 (`app/memory/conversation.py`)

SQLite 기반 4개 테이블로 대화를 영구 저장합니다:

| 테이블 | 용도 |
|--------|------|
| `users` | 사용자 정보 + 심리 프로필 (JSON) |
| `conversations` | 대화 세션 관리 |
| `messages` | 메시지 저장 (역할, 내용, 메타데이터) |
| `summaries` | 대화 요약 (turn 범위별) |

- **재접속 복원**: 브라우저 새로고침/새 탭에서도 이전 대화 복원
- **요약+최근 메시지 분리**: 요약된 범위는 요약으로, 이후는 원본 메시지로 표시

### 자동 요약 (`app/memory/summarizer.py`)

- 5턴(10메시지)마다 LLM 기반 자동 요약 트리거
- 감정 상태, 요청 음악 유형, 추천 만족도 중심으로 3줄 이내 요약
- 재접속 시 이전 대화 컨텍스트 복원에 활용

### 사용자 프로필 (`app/memory/user_profile.py`)

추천 결과 기반으로 사용자 프로필을 자동 갱신합니다:

- **선호 장르**: 추천 곡 장르 빈도 기반 (최대 10개)
- **어쿠스틱 성향**: acousticness 평균값
- **기분 이력**: 최근 20개 기분 기록
- **좋아한 곡**: 최근 20개 liked 곡

## 평가 방법

### 자동 평가 (`evaluation/run_eval.py`)

`evaluation/eval_queries.json`에 정의된 테스트 쿼리셋을 자동 실행하여 4가지 지표를 측정합니다:

| 지표 | 설명 | 목표 |
|------|------|------|
| **B. 할루시네이션** | 추천 곡이 DB에 실존하는 비율 | >= 95% |
| **C. Intent 정확도** | Gate Agent 분류 정확도 | >= 80% |
| **G. Spotify 매칭률** | 추천 곡의 Spotify URL 매칭 비율 | >= 60% |
| **Latency** | 평균 E2E 응답 시간 | <= 15초 |

### Edge Case 테스트

빈 입력, 의미 없는 텍스트, 초장문, 영어, 모순 감정, DB 미존재 곡, 범위 외 질문, 위험 신호 등 8개 엣지 케이스를 자동 테스트합니다.

### 수동 평가 (`evaluation/eval_app.py`)

Streamlit 기반 평가 인터페이스에서 추천 결과에 대해 수동 스코어링(A/D/F)을 수행할 수 있습니다.

```bash
# 자동 평가 실행
python evaluation/run_eval.py

# 수동 평가 UI
streamlit run evaluation/eval_app.py
```

결과는 `evaluation/results/` 디렉토리에 JSON으로 저장됩니다.

## 프로젝트 구조

```
music-chatbot/
├── streamlit_app.py              # 메인 Streamlit UI
├── app/
│   ├── config.py                 # 환경변수 설정
│   ├── orchestrator.py           # Gate → Music → Care 파이프라인 조율
│   ├── agents/
│   │   ├── gate_agent.py         # 의도 분류 + 안전 체크
│   │   ├── music_agent.py        # ReAct 도구 호출 루프
│   │   └── care_agent.py         # 공감 응답 생성
│   ├── tools/
│   │   ├── tool_executor.py      # 도구 라우팅 및 실행
│   │   ├── search_by_features.py # 오디오 피처 기반 검색
│   │   ├── search_by_description.py # 벡터 검색
│   │   ├── lookup_song.py        # 곡 정보 조회
│   │   ├── mental_health_songs.py # 멘탈헬스 라벨 필터링
│   │   ├── reranker.py           # 다중 기준 융합 리랭킹
│   │   ├── iso_playlist.py       # 동질 원리 플레이리스트
│   │   └── presets.py            # 상황별 오디오 피처 프리셋
│   ├── data/
│   │   ├── loader.py             # CSV 로드 + 전처리
│   │   ├── embedder.py           # 배치 임베딩 + ChromaDB 저장
│   │   └── song_describer.py     # 곡 설명 생성
│   ├── memory/
│   │   ├── conversation.py       # SQLite 대화 영속성
│   │   ├── summarizer.py         # LLM 기반 대화 요약
│   │   └── user_profile.py       # 사용자 선호도 프로필
│   ├── guardrails/
│   │   ├── safety.py             # 위험 신호 감지 + 긴급 응답
│   │   └── output_validator.py   # 출력 금지 표현 필터링
│   ├── prompts/
│   │   ├── gate_prompt.py        # Gate Agent 시스템 프롬프트
│   │   ├── music_agent_prompt.py # Music Agent 시스템 프롬프트
│   │   ├── care_prompt.py        # Care Agent 시스템 프롬프트
│   │   └── description_prompt.py # 곡 설명 생성 프롬프트
│   └── spotify/
│       ├── spotify_client.py     # Spotify API 클라이언트
│       └── spotify_config.py     # Spotify 설정
├── data/
│   ├── Music_recommendation.csv  # 음악 데이터셋
│   ├── chroma_db/                # ChromaDB 벡터 저장소
│   └── mindtune.db               # SQLite 대화 DB
├── evaluation/
│   ├── run_eval.py               # 자동 평가 스크립트
│   ├── eval_app.py               # 수동 평가 UI
│   └── eval_queries.json         # 테스트 쿼리셋
├── tests/
│   ├── test_gate_agent.py        # Gate Agent 테스트
│   ├── test_guardrails.py        # 안전장치 테스트
│   ├── test_memory.py            # 메모리 테스트
│   └── test_tools.py             # 도구 테스트
├── eda/                          # 탐색적 데이터 분석 노트북
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
