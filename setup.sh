#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "==> uv 미설치. 설치를 진행합니다."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> uv venv 생성"
uv venv

echo "==> playwright 의존성 설치"
uv sync

echo "==> Chromium 다운로드"
uv run playwright install chromium

echo "==> 시스템 의존성 설치 (sudo 요구될 수 있음)"
uv run playwright install-deps chromium || true

mkdir -p images

echo
echo "setup 완료."
echo "다음 단계:"
echo "  1) config.py 의 IMAGE_DIR, START_SHOT, END_SHOT 등을 확인"
echo "  2) images/ 에 {shotNumber}.png 또는 {shotNumber}.jpg 배치"
echo "  3) openart.ai 에 미리 로그인한 크롬 프로필 준비"
echo "  4) ./run.sh 실행"
