"""openart.ai 샷 자동화 배치 스크립트.

gen.json 의 샷을 순회하면서
    1) 로컬 이미지 업로드
    2) 업로드 완료 대기
    3) 영어 프롬프트 입력
    4) 제출 (기본: Ctrl+Enter)
를 반복한다. 기존 Chrome (--remote-debugging-port=9222) 세션에 CDP 로 붙는다.
"""

from __future__ import annotations

import base64
import json
import logging
import platform
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    Page,
    Playwright,
    TimeoutError as PWTimeout,
    sync_playwright,
)

import config

# ---------------------------------------------------------------------------
# 로깅 (콘솔 + logs/run_YYYYMMDD_HHMMSS.log)
# ---------------------------------------------------------------------------
config.LOG_DIR.mkdir(parents=True, exist_ok=True)
_log_path = config.LOG_DIR / f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"
_fmt = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
_console = logging.StreamHandler(stream=sys.stdout)
_console.setFormatter(_fmt)
_file = logging.FileHandler(_log_path, encoding="utf-8")
_file.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_console, _file])
log = logging.getLogger("openart")
log.info("로그 파일: %s", _log_path)


# ---------------------------------------------------------------------------
# 샷 데이터
# ---------------------------------------------------------------------------
@dataclass
class Shot:
    number: int | str
    prompt: str
    image: Optional[Path]
    image_end: Optional[Path] = None
    extra_refs: list[Path] = None  # text_ref 모드 전용 추가 레퍼런스 이미지 목록

    def __post_init__(self):
        if self.extra_refs is None:
            self.extra_refs = []


def load_shots() -> list[Shot]:
    data = json.loads(config.GEN_JSON.read_text(encoding="utf-8"))
    flat: list[Shot] = []
    for scene in data.get("storyboard", []):
        for s in scene.get("shots", []):
            n = s.get("shotNumber")
            if n is not None:
                if isinstance(n, int):
                    pass
                elif isinstance(n, str):
                    n = n.strip()
                    if n.isdigit():
                        n = int(n)
                else:
                    log.warning("shotNumber 타입 이상, 스킵: %r", n)
                    n = None
            prompt = (
                s.get("videoPrompt", {}).get("englishPrompt") or ""
            ).strip()
            if n is None or not prompt:
                log.warning("shot skipped (missing number/prompt): %r", s.get("shotId"))
                continue
            img = resolve_image(n)
            flat.append(Shot(
                number=n,
                prompt=prompt,
                image=img,
                image_end=resolve_end_image(n),
                extra_refs=resolve_extra_refs(n, img),
            ))

    proc = getattr(config, "PROC_SHOTS", None)
    if proc:
        by_number = {s.number: s for s in flat}
        selected: list[Shot] = []
        missing: list[int | str] = []
        for n in proc:
            s = by_number.get(n)
            if s is None:
                missing.append(n)
                continue
            selected.append(s)
        if missing:
            log.warning(
                "PROC_SHOTS 중 gen.json 에 없는 샷 %d개 스킵: %s",
                len(missing), missing,
            )
        return selected

    flat.sort(key=lambda x: _shot_num_sort_key(x.number))
    
    lo_k = _shot_num_sort_key(config.START_SHOT) if config.START_SHOT is not None else None
    hi_k = _shot_num_sort_key(config.END_SHOT) if config.END_SHOT is not None else None

    def _in_range(n: int | str) -> bool:
        k = _shot_num_sort_key(n)
        if lo_k is not None and k < lo_k:
            return False
        if hi_k is not None and k > hi_k:
            return False
        return True

    return [s for s in flat if _in_range(s.number)]

def _shot_num_sort_key(n: int | str) -> list:
    parts = []
    for seg in re.split(r"(\d+)", str(n)):
        if seg.isdigit():
            parts.append((int(seg), ""))
        elif seg:
            parts.append((float("inf"), seg))
    return parts


def _resolve_image_with_patterns(n: int | str, patterns: tuple[str, ...]) -> Optional[Path]:
    for pattern in patterns:
        stem = pattern.format(n=n)
        for ext in config.IMAGE_EXTS:
            p = config.IMAGE_DIR / f"{stem}{ext}"
            if p.exists():
                return p
    return None


def resolve_image(n: int | str) -> Optional[Path]:
    """config.IMAGE_NAME_PATTERNS 우선순위에 따라 시작 이미지 파일을 찾는다.

    각 패턴마다 config.IMAGE_EXTS 를 순회해 최초로 존재하는 파일 반환.
    """
    return _resolve_image_with_patterns(n, config.IMAGE_NAME_PATTERNS)


def resolve_end_image(n: int | str) -> Optional[Path]:
    """config.IMAGE_END_NAME_PATTERNS 우선순위에 따라 끝 이미지 파일을 찾는다.

    파일이 없으면 None (= end frame 업로드 안 함).
    """
    patterns = getattr(config, "IMAGE_END_NAME_PATTERNS", ())
    if not patterns:
        return None
    return _resolve_image_with_patterns(n, patterns)


def _natural_sort_key(p: Path) -> list:
    """파일명을 알파벳/숫자 오름차순으로 정렬하기 위한 키. (예: -a < -b < -aa)"""
    parts = []
    for seg in re.split(r"(\d+)", p.name):
        parts.append((int(seg), "") if seg.isdigit() else (float("inf"), seg))
    return parts


def resolve_extra_refs(n: int | str, main_img: Optional[Path]) -> list[Path]:
    """text_ref 모드용 추가 레퍼런스 이미지 목록을 반환한다.

    main_img 의 stem(예: "shot_1_image")을 기준으로
    IMAGE_DIR 에서 ``<stem>-*.{ext}`` 패턴의 파일을 수집하되,
    IMAGE_END_NAME_PATTERNS 에 해당하는 파일(-e 등)은 제외한다.
    결과는 알파벳/숫자 오름차순으로 정렬된다.
    """
    if main_img is None:
        return []

    stem = main_img.stem  # 예: "shot_1_image"

    # 제외할 stem 집합 (IMAGE_END_NAME_PATTERNS 기반)
    end_patterns = getattr(config, "IMAGE_END_NAME_PATTERNS", ())
    excluded_stems: set[str] = set()
    for pat in end_patterns:
        excluded_stems.add(pat.format(n=n))

    candidates: list[Path] = []
    for ext in config.IMAGE_EXTS:
        for p in config.IMAGE_DIR.glob(f"{stem}-*{ext}"):
            if p.stem in excluded_stems:
                continue
            candidates.append(p)

    # 중복 제거 후 자연 정렬
    seen: set[Path] = set()
    unique = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    unique.sort(key=_natural_sort_key)
    return unique


# ---------------------------------------------------------------------------
# 브라우저 연결
# ---------------------------------------------------------------------------
def connect_page(pw: Playwright) -> Page:
    log.info("CDP 연결 시도: %s", config.CDP_URL)
    browser = pw.chromium.connect_over_cdp(config.CDP_URL)
    if not browser.contexts:
        raise RuntimeError("크롬 컨텍스트가 없습니다. 브라우저를 먼저 실행하세요.")
    context = browser.contexts[0]

    # 열린 탭 목록 로깅 (디버깅용)
    log.info("기존 탭 %d개:", len(context.pages))
    for i, p in enumerate(context.pages):
        try:
            log.info("  [%d] %s", i, p.url)
        except Exception:
            log.info("  [%d] <url 읽기 실패>", i)

    # openart create-video/animate-video 가 이미 열려있으면 재사용.
    target_markers = ("create-video", "animate-video")
    page: Optional[Page] = None
    for p in context.pages:
        try:
            url = p.url
        except Exception:
            continue
        if "openart.ai" in url and any(m in url for m in target_markers):
            page = p
            log.info("기존 openart 탭 재사용: %s", url)
            break

    if page is None:
        log.info("새 탭 열기 → %s", config.TARGET_URL)
        page = context.new_page()
        page.goto(config.TARGET_URL, wait_until="domcontentloaded",
                  timeout=config.NAV_TIMEOUT * 1000)
    elif config.TARGET_URL not in page.url:
        log.info("탭 URL 불일치 → %s 로 이동", config.TARGET_URL)
        page.goto(config.TARGET_URL, wait_until="domcontentloaded",
                  timeout=config.NAV_TIMEOUT * 1000)

    page.bring_to_front()
    page.wait_for_selector(config.DROPZONE_ROOT,
                           timeout=config.NAV_TIMEOUT * 1000)
    log.info("✅ 페이지 준비 완료 (현재 URL: %s)", page.url)
    return page


# ---------------------------------------------------------------------------
# 업로드 / 입력 / 제출
# ---------------------------------------------------------------------------
_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _set_input_with_fallback(page: Page, input_selector: str, drop_selector: str,
                             img: Path) -> None:
    """hidden input 에 set_input_files 시도, 실패 시 DataTransfer 이벤트 드롭."""
    try:
        page.locator(input_selector).first.set_input_files(str(img))
        return
    except Exception as exc:
        log.warning("set_input_files 실패, DataTransfer 폴백 시도: %s", exc)

    data_b64 = base64.b64encode(img.read_bytes()).decode("ascii")
    mime = _MIME.get(img.suffix.lower(), "application/octet-stream")
    page.evaluate(
        """
        async ([selector, name, mime, b64]) => {
            const root = document.querySelector(selector);
            if (!root) throw new Error("dropzone not found");
            const bin = atob(b64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            const file = new File([bytes], name, { type: mime });
            const dt = new DataTransfer();
            dt.items.add(file);
            for (const type of ["dragenter", "dragover", "drop"]) {
                const ev = new DragEvent(type, {
                    bubbles: true, cancelable: true, dataTransfer: dt,
                });
                root.dispatchEvent(ev);
            }
        }
        """,
        [drop_selector, img.name, mime, data_b64],
    )


# ---------- Text with Reference 모드 ----------
def upload_image_tref(page: Page, img: Path) -> None:
    _set_input_with_fallback(page, config.FILE_INPUT, config.VISUAL_REF_ROOT, img)


# ---------- Start/End Frame 모드 ----------
def upload_image_sef(page: Page, img: Path, slot: int = 0) -> None:
    """SEF 모드 슬롯에 이미지 주입. slot=0 → start frame, slot=1 → end frame."""
    try:
        page.locator(config.SEF_FILE_INPUT).nth(slot).set_input_files(str(img))
        return
    except Exception as exc:
        log.warning("[SEF] slot=%d set_input_files 실패, DataTransfer 폴백: %s", slot, exc)

    data_b64 = base64.b64encode(img.read_bytes()).decode("ascii")
    mime = _MIME.get(img.suffix.lower(), "application/octet-stream")
    # slot 번째 파일 input 의 부모 컨테이너를 드롭 타겟으로 사용.
    page.evaluate(
        """
        async ([inputSelector, slot, name, mime, b64]) => {
            const inputs = document.querySelectorAll(inputSelector);
            const input = inputs[slot];
            if (!input) throw new Error(`SEF file input not found at slot ${slot}`);
            const root = input.closest('.relative.h-full.w-full') || input.parentElement;
            const bin = atob(b64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            const file = new File([bytes], name, { type: mime });
            const dt = new DataTransfer();
            dt.items.add(file);
            for (const type of ["dragenter", "dragover", "drop"]) {
                const ev = new DragEvent(type, {
                    bubbles: true, cancelable: true, dataTransfer: dt,
                });
                root.dispatchEvent(ev);
            }
        }
        """,
        [config.SEF_FILE_INPUT, slot, img.name, mime, data_b64],
    )


def read_counter(page: Page) -> int:
    """Text with Reference 모드의 업로드 카운터(n/N)의 n 값. 못 읽으면 0."""
    text = page.evaluate(
        "(sel) => (document.querySelector(sel)?.innerText) || ''",
        config.VISUAL_REF_ROOT,
    )
    m = re.search(r"(\d+)/\d+", text or "")
    return int(m.group(1)) if m else 0


class ResetError(RuntimeError):
    """리셋 실패: 전체 실행을 중단해야 한다."""


# ---------- 모드 선택 ----------
def select_mode(page: Page, mode: str) -> None:
    sel = config.MODE_RADIO[mode]
    btn = page.locator(sel).first
    if btn.count() == 0:
        raise RuntimeError(f"모드 라디오 버튼 미발견: {sel}")
    if btn.get_attribute("aria-checked") == "true":
        return
    btn.click()
    time.sleep(config.WAIT_AFTER_MODE)


# ---------- Text with Reference 업로드/리셋/대기 ----------
def wait_for_upload_tref(page: Page, baseline: int) -> None:
    deadline = time.time() + config.UPLOAD_TIMEOUT
    while time.time() < deadline:
        if read_counter(page) >= baseline + 1:
            return
        time.sleep(0.3)
    raise PWTimeout(
        f"업로드 완료 감지 실패 (baseline={baseline}, >{config.UPLOAD_TIMEOUT}s)"
    )


def _js_click_all(page: Page, selector: str) -> int:
    """opacity-0/pointer-events-none 등 CSS 차단을 우회하기 위해 JS로 모든 매칭 버튼 클릭.

    반환: 클릭한 개수.
    """
    return page.evaluate(
        """(sel) => {
            const els = Array.from(document.querySelectorAll(sel));
            els.forEach(el => el.click());
            return els.length;
        }""",
        selector,
    )


def reset_references_tref(page: Page) -> None:
    """모든 × 버튼을 JS로 클릭하여 업로드된 이미지를 제거. 카운터가 0이 될 때까지 대기."""
    for _ in range(20):
        clicked = _js_click_all(page, config.REF_REMOVE_BUTTON)
        if clicked == 0:
            break
        time.sleep(0.15)

    deadline = time.time() + config.RESET_TIMEOUT
    while time.time() < deadline:
        if read_counter(page) == 0:
            return
        time.sleep(0.2)
    raise ResetError(
        f"[Text] 이미지 리셋 실패: 카운터가 0 으로 돌아오지 않음 (>{config.RESET_TIMEOUT}s)"
    )


# ---------- Start/End Frame 업로드/리셋/대기 ----------
def wait_for_upload_sef(page: Page, baseline: int = 0) -> None:
    """Remove 버튼 개수가 baseline+1 이상이 될 때까지 대기.

    baseline=0 → 한 장 업로드 후 사용 (start frame).
    baseline=1 → start 가 이미 올라간 뒤 end frame 업로드 후 사용.
    """
    deadline = time.time() + config.UPLOAD_TIMEOUT
    while time.time() < deadline:
        if page.locator(config.SEF_REMOVE_BUTTON).count() >= baseline + 1:
            return
        time.sleep(0.3)
    raise PWTimeout(
        f"[SEF] 업로드 완료 감지 실패 (baseline={baseline}, >{config.UPLOAD_TIMEOUT}s)"
    )


def reset_references_sef(page: Page) -> None:
    """Remove 버튼을 JS 로 클릭해 start/end frame 제거, 사라질 때까지 대기."""
    for _ in range(5):
        clicked = _js_click_all(page, config.SEF_REMOVE_BUTTON)
        if clicked == 0:
            break
        time.sleep(0.15)

    deadline = time.time() + config.RESET_TIMEOUT
    while time.time() < deadline:
        if page.locator(config.SEF_REMOVE_BUTTON).count() == 0:
            return
        time.sleep(0.2)
    raise ResetError(
        f"[SEF] 이미지 리셋 실패: Remove 버튼이 사라지지 않음 (>{config.RESET_TIMEOUT}s)"
    )


# ---------- 모드 디스패처 ----------
def resolve_mode(shot_number: int | str) -> str:
    """shot_number 에 해당하는 모드를 반환한다.

    config.SHOT_MODE 가 list/set 이면 포함 여부로 MODE_TEXT_REF 판단.
    (포함 → MODE_TEXT_REF, 미포함 → DEFAULT_MODE)
    """
    shot_mode = config.SHOT_MODE
    if isinstance(shot_mode, dict):
        return shot_mode.get(shot_number, config.DEFAULT_MODE)
    # list / set / tuple → 포함되면 MODE_TEXT_REF
    return config.MODE_TEXT_REF if shot_number in shot_mode else config.DEFAULT_MODE


def upload_for_mode(page: Page, mode: str, img: Path) -> None:
    if mode == config.MODE_TEXT_REF:
        upload_image_tref(page, img)
    else:
        upload_image_sef(page, img)


def wait_upload_for_mode(page: Page, mode: str) -> None:
    if mode == config.MODE_TEXT_REF:
        wait_for_upload_tref(page, baseline=0)
    else:
        wait_for_upload_sef(page)


def reset_references_for_mode(page: Page, mode: str) -> None:
    if mode == config.MODE_TEXT_REF:
        reset_references_tref(page)
    else:
        reset_references_sef(page)


# macOS 에서는 Select-All 이 Meta+A(⌘+A), Linux/Windows 는 Control+A.
_SELECT_ALL = "Meta+A" if platform.system() == "Darwin" else "Control+A"


def _focus_editor(page: Page) -> None:
    """ProseMirror 에디터에 포커스. sticky nav 등에 클릭이 가려지면 JS focus 로 폴백."""
    editor = page.locator(config.PROMPT_EDITOR).first
    try:
        editor.click(timeout=3000)
        return
    except PWTimeout:
        pass
    page.evaluate(
        "(sel) => document.querySelector(sel)?.focus()",
        config.PROMPT_EDITOR,
    )


def _clear_editor(page: Page) -> None:
    """에디터 전체 선택 후 삭제. 플랫폼별 단축키를 사용한다.

    macOS: Meta+A (⌘+A) → Backspace
    Linux/Windows: Control+A → Backspace
    JS 직접 초기화로 2차 보장.
    """
    # 1차: 키보드 단축키
    page.keyboard.press(_SELECT_ALL)
    page.keyboard.press("Backspace")
    # 2차: 실제로 비워졌는지 JS 로 확인 후 남아있으면 강제 초기화
    remaining = page.evaluate(
        "(sel) => (document.querySelector(sel)?.innerText || '').trim()",
        config.PROMPT_EDITOR,
    )
    if remaining:
        log.warning("키보드 리셋 불완전 — JS 강제 초기화 시도")
        page.evaluate(
            """
            (sel) => {
                const el = document.querySelector(sel);
                if (!el) return;
                // ProseMirror 에 빈 단락 하나만 남긴다
                el.innerHTML = '<p><br></p>';
                el.dispatchEvent(new InputEvent('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
            """,
            config.PROMPT_EDITOR,
        )


def reset_prompt(page: Page) -> None:
    """프롬프트 에디터 내용을 비운다."""
    try:
        _focus_editor(page)
        _clear_editor(page)
    except Exception as exc:
        log.warning("프롬프트 리셋 경고: %s", exc)


def fill_prompt(page: Page, text: str) -> None:
    _focus_editor(page)
    # 기존 내용 제거 후 새 텍스트 입력
    _clear_editor(page)
    page.locator(config.PROMPT_EDITOR).first.type(text, delay=5)


# ---------- 생성 옵션 (submit 직전 적용) ----------
def ensure_audio_off(page: Page) -> None:
    """Audio 토글이 On 이면 Off 로 끈다. 이미 Off 면 아무것도 하지 않는다."""
    btn = page.locator(config.AUDIO_TOGGLE_BUTTON).first
    if btn.count() == 0:
        log.warning("Audio 토글 버튼 미발견, 스킵")
        return
    if btn.get_attribute("aria-checked") == "true":
        btn.click()
        log.info("  → Audio Off 변경")


def configure_output(page: Page) -> None:
    """Output popover 를 열어 Duration / Resolution 을 설정값에 맞춘다.

    트리거 표시 텍스트가 이미 "{VIDEO_DURATION} | {VIDEO_RESOLUTION}" 와 일치하면 스킵.
    """
    target_label = f"{config.VIDEO_DURATION} | {config.VIDEO_RESOLUTION}"
    trigger = page.locator(config.OUTPUT_TRIGGER).first
    if trigger.count() == 0:
        log.warning("Output 트리거 미발견, 스킵")
        return

    try:
        current_label = trigger.locator(config.OUTPUT_TRIGGER_VALUE).first.inner_text(timeout=1000).strip()
    except Exception:
        current_label = ""
    if current_label == target_label:
        return

    trigger.click()
    page.locator(config.OUTPUT_DIALOG).wait_for(timeout=3000)

    # Duration: Home 으로 최소값 이동 후 (target - min) 회 ArrowRight
    target_dur = int(config.VIDEO_DURATION.rstrip("sS"))
    slider = page.locator(config.OUTPUT_DURATION_SLIDER).first
    cur_dur = int(slider.get_attribute("aria-valuenow") or "0")
    if cur_dur != target_dur:
        slider.focus()
        vmin = int(slider.get_attribute("aria-valuemin") or "3")
        page.keyboard.press("Home")
        steps = target_dur - vmin
        for _ in range(max(0, steps)):
            page.keyboard.press("ArrowRight")
        time.sleep(0.2)

    # Resolution
    res_radio = page.locator(
        f'{config.OUTPUT_RESOLUTION_RADIO}:has-text("{config.VIDEO_RESOLUTION}")'
    ).first
    if res_radio.count() and res_radio.get_attribute("aria-checked") != "true":
        res_radio.click()
        time.sleep(0.2)

    # 닫기
    page.keyboard.press("Escape")
    log.info("  → Output 설정: %s", target_label)


def submit(page: Page) -> None:
    strat = config.SUBMIT_STRATEGY
    if strat == "ctrl_enter":
        page.keyboard.press("Control+Enter")
        return
    if strat == "enter":
        page.keyboard.press("Enter")
        return
    if strat == "generate_button":
        for label in config.SUBMIT_BUTTON_LABELS:
            btn = page.locator(
                f'button[type="submit"]:has-text("{label}")'
            ).first
            if btn.count() and btn.is_visible() and btn.is_enabled():
                btn.click()
                log.info("  → '%s' 버튼 클릭", label)
                return
        raise RuntimeError(
            f"제출 버튼 탐색 실패 (labels={config.SUBMIT_BUTTON_LABELS})"
        )
    raise ValueError(f"unknown SUBMIT_STRATEGY: {strat}")


# ---------------------------------------------------------------------------
# 샷 처리
# ---------------------------------------------------------------------------
def process_shot(page: Page, shot: Shot) -> None:
    mode = resolve_mode(shot.number)
    has_end = (mode == config.MODE_START_END) and (shot.image_end is not None)
    has_extra = (mode == config.MODE_TEXT_REF) and bool(shot.extra_refs)
    tag = f"샷 {shot.number:>3} [{mode}{'+end' if has_end else ''}{'+extra×'+str(len(shot.extra_refs)) if has_extra else ''}]"
    if has_end:
        log.info("%s: 시작 (image=%s, end=%s)", tag, shot.image.name, shot.image_end.name)
    elif has_extra:
        log.info("%s: 시작 (image=%s, extra_refs=%s)", tag, shot.image.name,
                 [p.name for p in shot.extra_refs])
    else:
        log.info("%s: 시작 (image=%s)", tag, shot.image.name)

    page.wait_for_selector(config.DROPZONE_ROOT, timeout=config.NAV_TIMEOUT * 1000)

    # 1) 모드 선택 (radio 클릭)
    select_mode(page, mode)

    # 2) 리셋 (이미지 + 텍스트)
    reset_references_for_mode(page, mode)
    reset_prompt(page)
    log.info("%s: 🧹 리셋 완료", tag)
    time.sleep(config.WAIT_AFTER_RESET)

    # 3) 이미지 업로드 → 대기
    if has_end:
        upload_image_sef(page, shot.image, slot=0)
        log.info("%s: start 업로드 요청", tag)
        wait_for_upload_sef(page, baseline=0)
        log.info("%s: ✅ start 업로드 완료", tag)
        upload_image_sef(page, shot.image_end, slot=1)
        log.info("%s: end 업로드 요청", tag)
        wait_for_upload_sef(page, baseline=1)
        log.info("%s: ✅ end 업로드 완료", tag)
    elif has_extra:
        # text_ref 모드: 메인 이미지 먼저, 이후 추가 레퍼런스 이미지 순서대로 업로드
        upload_image_tref(page, shot.image)
        log.info("%s: 메인 이미지 업로드 요청 (%s)", tag, shot.image.name)
        wait_for_upload_tref(page, baseline=0)
        log.info("%s: ✅ 메인 이미지 업로드 완료", tag)
        for idx, ref_img in enumerate(shot.extra_refs, start=1):
            upload_image_tref(page, ref_img)
            log.info("%s: 추가 레퍼런스[%d/%d] 업로드 요청 (%s)",
                     tag, idx, len(shot.extra_refs), ref_img.name)
            wait_for_upload_tref(page, baseline=idx)
            log.info("%s: ✅ 추가 레퍼런스[%d/%d] 업로드 완료", tag, idx, len(shot.extra_refs))
    else:
        upload_for_mode(page, mode, shot.image)
        log.info("%s: 업로드 요청 보냄", tag)
        wait_upload_for_mode(page, mode)
        log.info("%s: ✅ 업로드 완료", tag)

    # 4) 텍스트 입력 → 대기
    fill_prompt(page, shot.prompt)
    log.info("%s: ✅ 텍스트 입력 완료 (%d자)", tag, len(shot.prompt))
    time.sleep(config.WAIT_AFTER_TEXT)

    # 5) 생성 옵션 설정 (Audio Off, Output Duration/Resolution)
    ensure_audio_off(page)
    configure_output(page)

    # 6) 제출 → 대기
    submit(page)
    log.info("%s: ✅ 제출 (%s)", tag, config.SUBMIT_STRATEGY)
    time.sleep(config.WAIT_AFTER_SUBMIT)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    shots = load_shots()
    if not shots:
        log.error("처리할 샷이 없습니다. PROC_SHOTS / START_SHOT / END_SHOT / gen.json 확인.")
        return 1

    if getattr(config, "PROC_SHOTS", None):
        log.info(
            "총 %d개 샷 (PROC_SHOTS 순서: %s) 처리 예정",
            len(shots), [s.number for s in shots],
        )
    else:
        log.info(
            "총 %d개 샷 (#%d ~ #%d) 처리 예정",
            len(shots), shots[0].number, shots[-1].number,
        )

    missing = [s.number for s in shots if s.image is None]
    if missing:
        log.warning(
            "⚠️  이미지 없는 샷 %d개 → 처리 시 스킵 예정: %s (IMAGE_DIR=%s)",
            len(missing), missing, config.IMAGE_DIR,
        )

    ok = 0
    failed: list[int] = []
    skipped: list[int] = []
    aborted = False
    with sync_playwright() as pw:
        page = connect_page(pw)
        for shot in shots:
            if shot.image is None:
                log.warning(
                    "⏭️  샷 %d 스킵: 이미지 파일 없음 (IMAGE_DIR=%s)",
                    shot.number, config.IMAGE_DIR,
                )
                skipped.append(shot.number)
                continue
            try:
                process_shot(page, shot)
                ok += 1
            except ResetError as exc:
                log.error("💥 리셋 실패로 전체 중단 (샷 %d): %s", shot.number, exc)
                failed.append(shot.number)
                _save_error_screenshot(page, shot.number)
                aborted = True
                break
            except Exception as exc:
                failed.append(shot.number)
                log.error("샷 %d 실패: %s", shot.number, exc)
                _save_error_screenshot(page, shot.number)

    log.info(
        "🎉 완료: 성공 %d / 스킵 %d / 실패 %d%s%s%s",
        ok,
        len(skipped),
        len(failed),
        f" (스킵 샷: {skipped})" if skipped else "",
        f" (실패 샷: {failed})" if failed else "",
        " [중단됨]" if aborted else "",
    )
    if aborted:
        return 3
    return 0 if not failed else 2


def _save_error_screenshot(page: Page, n: int | str) -> None:
    try:
        path = config.LOG_DIR / f"error_shot_{n}.png"
        page.screenshot(path=str(path), full_page=True)
        log.error("스크린샷 저장: %s", path)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
