# openart.ai 샷 자동화

`gen.json`의 모든 샷을 순회하며 openart.ai create-video 페이지에서
**이미지 업로드 → 영어 프롬프트 입력 → 제출**을 자동화한다.

## 요구 환경

- Ubuntu
- Google Chrome (또는 Chromium)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## 설치

```bash
./setup.sh
```

`uv`가 없으면 자동 설치되고, Playwright Chromium과 시스템 의존성까지 설치한다.

## 사용

1. `config.py`를 열어 아래 값을 확인/수정.
   - `IMAGE_DIR`: 샷 이미지 디렉터리 (기본 `./images/`).
     파일명은 `{shotNumber}.png` 또는 `{shotNumber}.jpg` (없으면 이미지
     없이 텍스트만 제출).
   - `START_SHOT`, `END_SHOT`: 처리할 샷 번호 범위 (inclusive, `None`이면
     처음/끝까지).
   - `UPLOAD_TIMEOUT`, `WAIT_AFTER_TEXT`, `WAIT_AFTER_SUBMIT`: 대기 시간(초).
   - `SUBMIT_STRATEGY`: `ctrl_enter` / `enter` / `submit_button`.
2. openart.ai에 **미리 로그인된** 크롬 프로필이 있어야 한다. 처음이라면
   `./run.sh`를 한 번 실행해 크롬을 띄운 뒤 해당 창에서 직접 로그인하고,
   로그인 상태가 유지된 채 `./run.sh`를 다시 실행한다.
3. 실행:

   ```bash
   ./run.sh
   ```

   `run.sh`는
   - `localhost:9222`에 이미 CDP 세션이 있으면 그걸 그대로 쓰고,
   - 없으면 `--remote-debugging-port=9222 --user-data-dir=...` 옵션으로
     크롬을 기동한 뒤 `openart_batch.py`를 실행한다.

## 동작

각 샷에 대해 순서대로:

1. 샷 번호에 해당하는 이미지 파일을 hidden `<input type="file">`에 주입
   (실패 시 `DataTransfer` 이벤트 폴백).
2. 업로드 카운터가 `n/15 (n≥1)`로 바뀔 때까지 대기 (최대
   `UPLOAD_TIMEOUT`초).
3. ProseMirror 에디터에 `Ctrl+A` → `Delete`로 초기화 후
   `startImagePrompt.englishPrompt` 입력.
4. `WAIT_AFTER_TEXT`초 대기.
5. `SUBMIT_STRATEGY`에 따라 제출 (기본 Ctrl+Enter).
6. `WAIT_AFTER_SUBMIT`초 대기 후 다음 샷으로.

실패 시 `error_shot_{번호}.png` 스크린샷을 남기고 다음 샷으로 이어간다.

## 트러블슈팅

- **`set_input_files` 실패 또는 업로드 안 됨**: 콘솔 로그에서
  `DataTransfer 폴백`이 떴는지 확인. 그래도 안 되면 페이지 DOM이 바뀐
  것. `config.py`의 `VISUAL_REF_ROOT`, `FILE_INPUT` 셀렉터를 최신으로
  업데이트한다.
- **Ctrl+Enter로 제출이 안 됨**: `config.py`에서
  `SUBMIT_STRATEGY = "submit_button"`으로 변경. 그래도 안 되면 실제
  Generate 버튼의 셀렉터를 확인해 `SUBMIT_BUTTON_HIDDEN`을 조정.
- **이전 샷 이미지가 다음 샷에 남아 있음**: openart UI가 리셋되지 않는
  경우. 현재 버전은 자동 제거 루틴이 없으므로, 수동으로 삭제 로직을
  추가해야 한다 (PR 환영). 임시 회피: 각 샷 사이 수동 개입, 또는 샷
  범위를 작게 끊어 실행.
- **포트 9222 이미 사용 중**: `lsof -i :9222`로 확인. 다른 크롬 인스턴스를
  닫거나 `CDP_URL`을 다른 포트로 바꾼다.
- **로그인 상태가 유지되지 않음**: `run.sh`가 사용하는 프로필 디렉터리는
  기본 `~/.config/google-chrome-openart`. 환경변수 `OPENART_PROFILE_DIR`
  로 바꿀 수 있다. 기존 일상 크롬 프로필과 **분리**되어 있어 처음엔
  로그인이 필요하다.

## 파일

| 경로 | 설명 |
|------|------|
| `config.py` | 모든 설정값 |
| `openart_batch.py` | 샷 루프 메인 |
| `setup.sh` | 최초 환경 구성 |
| `run.sh` | Chrome + 자동화 실행 |
| `images/` | 샷 이미지 (`1.png`, `2.jpg`, …) |
| `gen.json` | 스토리보드 원본 |
