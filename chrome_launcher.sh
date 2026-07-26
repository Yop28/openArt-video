# 공유 Chrome CDP 런처
#
# 4개의 OpenArt 자동화 프로젝트(openArt-video, openArt-Image,
# openArt-v_upscale, openArt-i_upscale) 가 동일한 Chrome 인스턴스/포트/프로필을
# 공유하도록 한다. 각 프로젝트의 run.sh 가 이 파일을 source 한 뒤
# `ensure_chrome` 을 호출하면:
#   - 9222 포트에 CDP 가 이미 떠 있으면 attach
#   - 떠 있지 않으면 setsid 로 새 Chrome 을 detached 기동 후 폴링
#
# 이 파일은 그 자체로 실행되지 않는다 — 반드시 source 로 사용.

# Bash 가 아니어도 source 가능하지만 setsid/배열을 쓰므로 bash 권장.

: "${OPENART_CDP_PORT:=9222}"
: "${OPENART_SHARED_PROFILE_DIR:=$HOME/.config/google-chrome-openart-shared}"
export OPENART_CDP_PORT
export OPENART_SHARED_PROFILE_DIR
export OPENART_CDP_URL="http://localhost:${OPENART_CDP_PORT}"

_openart_find_chrome_bin() {
    if [[ -n "${CHROME_BIN:-}" ]] && command -v "$CHROME_BIN" >/dev/null 2>&1; then
        return 0
    fi
    # macOS: .app 번들 내 실행파일 경로 우선 탐색
    local mac_chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    local mac_chromium="/Applications/Chromium.app/Contents/MacOS/Chromium"
    for mac_bin in "$mac_chrome" "$mac_chromium"; do
        if [[ -x "$mac_bin" ]]; then
            CHROME_BIN="$mac_bin"
            export CHROME_BIN
            return 0
        fi
    done
    # Linux / PATH 에 등록된 경우
    for cand in google-chrome google-chrome-stable chromium chromium-browser; do
        if command -v "$cand" >/dev/null 2>&1; then
            CHROME_BIN="$cand"
            export CHROME_BIN
            return 0
        fi
    done
    return 1
}

ensure_chrome() {
    local cdp_url="${OPENART_CDP_URL}"
    local profile_dir="${OPENART_SHARED_PROFILE_DIR}"

    if curl -sf "${cdp_url}/json/version" >/dev/null 2>&1; then
        echo "[chrome_launcher] 포트 ${OPENART_CDP_PORT} 에 이미 CDP 세션이 있습니다 → attach."
        echo "                  (다른 프로필로 띄워진 Chrome 이라면 openart.ai 로그인 누락으로 실패할 수 있음."
        echo "                   그 경우 해당 Chrome 을 닫고 run.sh 를 다시 실행하세요.)"
        return 0
    fi

    if ! _openart_find_chrome_bin; then
        echo "[chrome_launcher] Chrome 실행 파일을 찾지 못했습니다." >&2
        echo "                  CHROME_BIN 환경변수로 경로를 지정하거나 google-chrome 을 설치하세요." >&2
        return 1
    fi

    if [[ "$profile_dir" == "$HOME/.config/google-chrome" ]]; then
        echo "[chrome_launcher] Chrome 기본 데이터 디렉터리는 사용할 수 없습니다." >&2
        echo "                  Chrome 147+ 은 default user-data-dir 에서 --remote-debugging-port 를 거부합니다." >&2
        echo "                  OPENART_SHARED_PROFILE_DIR 를 다른 경로로 지정하세요." >&2
        return 1
    fi

    local first_run=0
    if [[ ! -d "$profile_dir" ]]; then
        mkdir -p "$profile_dir"
        first_run=1
    fi

    echo "[chrome_launcher] 디버깅 포트 ${OPENART_CDP_PORT} 로 Chrome 을 기동 (프로필: ${profile_dir})."
    # setsid 는 Linux 전용. macOS 에서는 nohup + & 로 대체.
    if command -v setsid >/dev/null 2>&1; then
        setsid "$CHROME_BIN" \
            --remote-debugging-port="${OPENART_CDP_PORT}" \
            --user-data-dir="${profile_dir}" \
            --window-size=1440,900 \
            --window-position=0,0 \
            --no-first-run \
            --no-default-browser-check \
            </dev/null >/dev/null 2>&1 &
        disown || true
    else
        nohup "$CHROME_BIN" \
            --remote-debugging-port="${OPENART_CDP_PORT}" \
            --user-data-dir="${profile_dir}" \
            --window-size=1440,900 \
            --window-position=0,0 \
            --no-first-run \
            --no-default-browser-check \
            </dev/null >/dev/null 2>&1 &
        disown || true
    fi

    if [[ "$first_run" == "1" ]]; then
        echo "[chrome_launcher] 최초 실행: openart.ai 에 수동 로그인한 뒤 자동화를 진행하세요."
    fi
    echo "[chrome_launcher] Ctrl+C 로 run.sh 를 중단해도 Chrome 은 계속 살아있습니다."

    local i
    for i in $(seq 1 40); do
        if curl -sf "${cdp_url}/json/version" >/dev/null 2>&1; then
            echo "[chrome_launcher] CDP 연결 확인 완료."
            return 0
        fi
        sleep 0.5
    done

    echo "[chrome_launcher] Chrome CDP 기동 실패 (20초 대기)." >&2
    return 1
}
