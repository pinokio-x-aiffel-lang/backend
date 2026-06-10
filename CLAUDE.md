# CLAUDE.md

## Git workflow
- When a task looks like new feature work, always ask "Should I create a new branch off `dev`?" before starting.
- Do not start the work until the user confirms, unless they explicitly say to continue on the current branch.
- Branch naming convention: suggest `feature/<short-description>`.
- When pushing to git, always push the current branch (`git push origin <current-branch>`). Never push directly to `main`, `master`, or `dev` unless the user explicitly asks.

## LLM 호출 규칙
- 모든 LLM 호출은 반드시 `src/llm/llm_caller.py`(`LlmCaller`)를 통해서만 한다.
- `src/llm/provider.py`(모델 메타·라우팅), `src/llm/client.py`(`LlmError` 등)도 이 경유 안에서만 사용한다.
- 금지: OpenAI/Anthropic 등 LLM SDK 직접 import, CLOVA Studio(HCX) 등 LLM 엔드포인트로 직접 HTTP 호출(`requests`/`httpx`/`aiohttp`), `src/llm` 밖에서의 자체 LLM 클라이언트 작성.
- 새 provider/모델이 필요하면 `src/llm` 안에 추가하고 `LlmCaller` 경유를 유지한다.
- 모델 호출 파라미터(provider/model/max_tokens/temperature)는 `src/llm/model_presets.py` 의 `ModelPreset` 에서만 가져온다(호출부 리터럴 금지). 상세는 `model-presets` 스킬.

## 테스트 결과 기록
- 테스트 결과는 항상 `tests/results/` 에 저장한다.
- 파일명: `[YYMMDD]_[단계]_[대상]_[작성자][_시리얼].md` + 동일 이름 `.json`. 모듈명의 `_`는 하이픈, 여러 단계는 `7-8`, 재실행은 끝에 `_01`·`_02`. (단계 번호는 `src/pipeline/runner.py` 10단계 기준)
- `.md` = 사람용 리포트(상단 필수: ①테스트 목적 ②검증 대상 모듈 ③도구로만 쓰인 모듈 ④일자/작성자), `.json` = 실제 결과 원자료를 동일 파일명으로 별도 저장하고 md에서 참조.
- 상세·템플릿: `tests/README.md`.