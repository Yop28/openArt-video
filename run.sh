#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# uv 가 ~/.local/bin 에 설치되어 있을 수 있는데(setup.sh 직후 셸 PATH 미반영 케이스)
# 현재 셸 PATH 에 없으면 추가한다.
if ! command -v uv >/dev/null 2>&1 && [[ -x "$HOME/.local/bin/uv" ]]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

# OS 감지 후 플랫폼에 맞는 Chrome 런처 선택
_OS="$(uname -s)"
case "$_OS" in
    Darwin)
        echo "[run.sh] OS: macOS → chrome_launcher.sh 사용"
        source "$HERE/chrome_launcher.sh"
        ;;
    Linux)
        echo "[run.sh] OS: Linux/Ubuntu → chrome_launcher-ubuntu.sh 사용"
        source "$HERE/chrome_launcher-ubuntu.sh"
        ;;
    *)
        echo "[run.sh] 지원하지 않는 OS: $_OS" >&2
        exit 1
        ;;
esac
ensure_chrome

# Chrome 이 프로필 선택 화면에 머물러 있거나 openart 탭이 아직 없으면
# 사용자가 수동으로 프로필을 선택하고 openart 에 진입할 시간을 벌어준다.
echo "[run.sh] openart.ai 탭을 여시고 Enter 를 누르면 자동화를 시작합니다 (건너뛰려면 바로 Enter)."
read -r -t 60 _ || echo "[run.sh] (타임아웃) 자동화를 시작합니다."

uv run python openart_batch.py
