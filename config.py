"""openart.ai 샷 자동화 설정값.

모든 튜닝 가능한 값은 이 파일에 모여 있다.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 대상 URL / CDP
# ---------------------------------------------------------------------------

# TARGET_URL = "https://openart.ai/suite/create-video/byte-plus-seedance-2"
TARGET_URL = "https://openart.ai/suite/create-video/kling-3-omni?folderId=AladG9A7Kb9bgevllvMx"
# 4개 OpenArt 프로젝트가 공유 Chrome 인스턴스를 쓰므로 chrome_launcher.sh 가
# OPENART_CDP_URL 을 export 한다. 단독 실행 시 default 9222 로 폴백.
CDP_URL = os.environ.get("OPENART_CDP_URL", "http://localhost:9222")

# ---------------------------------------------------------------------------
# 입력 파일
# ---------------------------------------------------------------------------
# PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path("/run/media/u/B62F9460757288E2/Work/신약/8C#/imgs/cuts/for_vds")
# 스토리보드 JSON 경로. storyboard[*].shots[*] 를 모두 이어 붙여 순회한다.
GEN_JSON = PROJECT_ROOT / "./storyboard.json"

# 샷 이미지가 모여 있는 디렉터리.
# 파일명 규칙:
#   1순위: img-{shotNumber}.{ext}
#   2순위: img-{shotNumber}-1.{ext}
# 절대경로로 바꿔도 된다.
IMAGE_DIR = PROJECT_ROOT / "./"

# 샷 이미지로 인정할 확장자 (우선순위 순서대로 탐색).
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# 이미지 파일명 후보 패턴. {n} 은 shotNumber 로 치환된다.
# 앞에서부터 순서대로 IMAGE_EXTS 를 조합해 검색한다.
IMAGE_NAME_PATTERNS = ("shot_{n}_image",)

# 끝 프레임(end frame) 이미지 파일명 후보 패턴. MODE_START_END 모드에서만 사용.
# 이 패턴으로 파일이 발견되면 start frame 업로드 후 end frame 도 함께 업로드된다.
# 발견되지 않으면 기존처럼 start frame 만으로 비디오를 생성한다.
IMAGE_END_NAME_PATTERNS = ("shot_{n}_image-e",)

# ---------------------------------------------------------------------------
# 처리 범위 (inclusive). None 이면 처음 / 끝.
# ---------------------------------------------------------------------------
START_SHOT: int | str | None = 1
END_SHOT: int | str | None = 1

# 명시적 샷 리스트. None 또는 [] 이면 START_SHOT/END_SHOT 사용.
# 비어있지 않은 리스트가 들어 있으면 START_SHOT/END_SHOT 는 무시되고
# 이 배열의 순서대로 처리된다. (예: [10, 5, 20] → 10 → 5 → 20)
# gen.json 에 없는 번호는 경고 후 스킵.
PROC_SHOTS: list[int | str] | None = []
# ---------------------------------------------------------------------------
# 대기 시간 (초)
# ---------------------------------------------------------------------------
# 업로드 완료를 감지할 때까지 최대 대기 시간
UPLOAD_TIMEOUT = 50
# 텍스트 입력 후 정적 대기 (에디터가 상태를 반영할 시간)
WAIT_AFTER_TEXT = 10
# 제출 후 다음 샷 진입 전 정적 대기 (생성은 백그라운드에서 계속됨)
WAIT_AFTER_SUBMIT = 30
# SPA 전환 / 네비게이션 대기
NAV_TIMEOUT = 30

# ---------------------------------------------------------------------------
# 제출 방식
# ---------------------------------------------------------------------------
# "generate_button" | "ctrl_enter" | "enter"
#   generate_button - data-generate-btn="true" 우선 클릭, 없으면 labels 순회 (기본)
#   ctrl_enter      - 키보드 Ctrl+Enter
#   enter           - 키보드 Enter
SUBMIT_STRATEGY = "generate_button"

# 신규 생성 버튼 속성 셀렉터 (최우선)
SUBMIT_BUTTON_GENERATOR = 'button[type="submit"][data-generate-btn="true"]'

# 제출 버튼 텍스트 우선순위 (폴백용)
SUBMIT_BUTTON_LABELS = ("Generate", "Unlimited")

# ---------------------------------------------------------------------------
# 로그 / 에러 출력 디렉터리
# ---------------------------------------------------------------------------
# 로그 디렉터리는 스크립트 위치 기준으로 고정 (PROJECT_ROOT 와 무관).
LOG_DIR = Path(__file__).resolve().parent / "logs"

# ---------------------------------------------------------------------------
# DOM 셀렉터 (UI 변경 시 여기만 수정)
# ---------------------------------------------------------------------------
DROPZONE_ROOT = '[data-prompt-root="true"]'
VISUAL_REF_ROOT = '[data-prompt-visual-references="true"]'
FILE_INPUT = f'{VISUAL_REF_ROOT} input[type="file"]'
PROMPT_EDITOR = (
    '[data-prompt-input="true"] [contenteditable="true"].ProseMirror'
)
CLEAR_PROMPT_BUTTON = 'button[aria-label="Clear Prompt"]'
SUBMIT_BUTTON_HIDDEN = '[data-prompt-input="true"] button[type="submit"]'
# 업로드된 썸네일 각각의 × 버튼
REF_REMOVE_BUTTON = (
    f'{VISUAL_REF_ROOT} button:has(svg[data-icon="CloseBold"])'
)

# Kling 3.0 Omni 최대 비주얼 레퍼런스 수 (UI 상 1/7 표시)
MAX_VISUAL_REFS = 7

# 이미지 리셋 타임아웃 (초) — 모든 × 클릭 후 카운터가 0 이 될 때까지.
RESET_TIMEOUT = 10

# ---------------------------------------------------------------------------
# 모드 (Text with Reference / Start/End Frame)
# ---------------------------------------------------------------------------
MODE_TEXT_REF = "text_with_reference"   # Text to Video (다중 비주얼 레퍼런스, 최대 7장)
MODE_START_END = "start_end_frame"      # Frame to Video (시작/끝 프레임 슬롯)

# UI 헤더 도구 이름 매핑
MODE_TOOL_NAMES = {
    MODE_TEXT_REF: "Text to Video",
    MODE_START_END: "Frame to Video",
}

# 헤더 도구 전환(Switch Tool) 셀렉터
TOOL_HEADER = 'header:has(button[aria-label="Switch tool"])'
TOOL_HEADER_TITLE = f'{TOOL_HEADER} h1'
TOOL_SWITCH_BUTTON = f'{TOOL_HEADER} button[aria-label="Switch tool"]'
SIDECAR_DIALOG = 'div[data-testid="creation-panel-sidecar"]'
SIDECAR_CLOSE_BUTTON = f'{SIDECAR_DIALOG} button[aria-label="Close"]'

# 기본 모드 (SHOT_MODE 에 없는 샷은 이 값 사용)
DEFAULT_MODE = MODE_START_END

# MODE_TEXT_REF 로 처리할 샷 번호 목록.
# 리스트에 포함된 샷은 자동으로 MODE_TEXT_REF, 나머지는 DEFAULT_MODE.
SHOT_MODE: list[int | str] = [1,"2-1","2-2","4-1",8,11]

# 리셋 직후 / 모드 전환 직후 정적 대기 (초)
WAIT_AFTER_RESET = 2
WAIT_AFTER_MODE = 0.5

# 모드 선택 radio 버튼 (구버전 UI 호환용 폴백)
MODE_SELECTOR = '[role="radiogroup"][aria-label="Mode Selector"]'
MODE_RADIO = {
    MODE_TEXT_REF:  f'{MODE_SELECTOR} button[role="radio"][value="text-to-video"]',
    MODE_START_END: f'{MODE_SELECTOR} button[role="radio"][value="image-to-video"]',
}

# Start/End Frame 모드 셀렉터
# 주의: SEF 모드의 파일 input 은 [data-prompt-root] 외부의 별도 패널에 있다.
# 또한 start/end 두 슬롯이 grid 로 존재하므로 .first 로 start 슬롯만 타겟.
SEF_FILE_INPUT = 'input[type="file"]:not([multiple])'
SEF_REMOVE_BUTTON = 'button[aria-label="Remove"]'

# ---------------------------------------------------------------------------
# 생성 옵션 (submit 직전 매 샷마다 적용)
# ---------------------------------------------------------------------------
# Audio: 항상 Off. 켜져 있으면(=aria-checked="true") 토글로 끄고, 이미 Off 면 패스.
AUDIO_TOGGLE_CONTAINER = 'div.group:has(div:text-is("Audio"))'
AUDIO_TOGGLE_BUTTON = f'{AUDIO_TOGGLE_CONTAINER} button[role="switch"]'

# Auto Polish & Multi-shot 스위치: 항상 Off.
AUTO_POLISH_SWITCH = 'div:has(> div:text-is("Auto Polish")) button[role="switch"]'
MULTI_SHOT_SWITCH = 'div:has(> div span:text-is("Multi-shot")) button[role="switch"]'

# Output 시간 / 해상도. submit 직전 매 샷마다 적용.
# VIDEO_DURATION 은 "Ns" 형식(슬라이더 aria-valuemin=3, valuemax=15 사이의 정수+s).
# VIDEO_RESOLUTION 은 라디오 버튼 텍스트 그대로 ("720p" / "1080p" / "4K").
VIDEO_DURATION = "8s"
VIDEO_RESOLUTION = "1080p"

# Output 트리거 (popover 여는 div, type=button + aria-haspopup="dialog")
OUTPUT_TRIGGER = 'div[aria-haspopup="dialog"]:has(div:text-is("Output"))'
# 트리거 안에 현재 값을 표시하는 텍스트 span (예: "16:9 | 8s | 1080p")
OUTPUT_TRIGGER_VALUE = 'span.truncate'
# 열린 popover 다이얼로그
OUTPUT_DIALOG = '[role="dialog"][data-state="open"]'
# Duration 슬라이더 (Radix slider)
OUTPUT_DURATION_SLIDER = f'{OUTPUT_DIALOG} [role="slider"]'
# Resolution 라디오 버튼들
OUTPUT_RESOLUTION_RADIO = f'{OUTPUT_DIALOG} [role="radiogroup"] button[role="radio"]'


