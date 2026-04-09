"""MindTune 데이터 초기화 스크립트

사용법:
    python reset.py          # 세션/대화 기록만 초기화 (임베딩 유지)
    python reset.py --all    # 임베딩 포함 전체 초기화
"""
import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

SESSION_FILES = [
    os.path.join(DATA_DIR, "mindtune.db"),
    os.path.join(DATA_DIR, ".user_id"),
]

EMBEDDING_DIR = os.path.join(DATA_DIR, "chroma_db")


def reset_session():
    for f in SESSION_FILES:
        if os.path.exists(f):
            os.remove(f)
            print(f"  삭제: {os.path.relpath(f, BASE_DIR)}")
        else:
            print(f"  없음: {os.path.relpath(f, BASE_DIR)} (이미 깨끗)")


def reset_embeddings():
    if os.path.exists(EMBEDDING_DIR):
        shutil.rmtree(EMBEDDING_DIR)
        print(f"  삭제: {os.path.relpath(EMBEDDING_DIR, BASE_DIR)}/")
    else:
        print(f"  없음: {os.path.relpath(EMBEDDING_DIR, BASE_DIR)}/ (이미 깨끗)")


if __name__ == "__main__":
    full = "--all" in sys.argv

    print("=== MindTune 초기화 ===\n")

    print("[1/2] 세션/대화 기록 초기화")
    reset_session()

    if full:
        print("\n[2/2] 임베딩 초기화 (chroma_db)")
        reset_embeddings()
        print("\n⚠️  다음 앱 실행 시 임베딩을 처음부터 다시 빌드합니다.")
    else:
        print("\n[2/2] 임베딩 유지 (--all 옵션으로 삭제 가능)")

    print("\n✅ 초기화 완료!")
