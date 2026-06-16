# CLAUDE.md

## Git workflow
- When a task looks like new feature work, always ask "Should I create a new branch off `dev`?" before starting.
- Do not start the work until the user confirms, unless they explicitly say to continue on the current branch.
- Branch naming convention: suggest `feat/<short-description>`.
- When pushing to git, always push the current branch (`git push origin <current-branch>`). Never push directly to `main`, `master`, or `dev` unless the user explicitly asks.
- Never add `Co-Authored-By` to commit messages.
- Full branch / commit / PR convention (single source of truth): `git-convention` 스킬.

## LLM 호출 규칙
- 모든 LLM 호출은 반드시 `src/llm/llm_caller.py`(`LlmCaller`)를 통해서만 한다.
- `src/llm/provider.py`(모델 메타·라우팅), `src/llm/client.py`(`LlmError` 등)도 이 경유 안에서만 사용한다.
- 금지: OpenAI/Anthropic 등 LLM SDK 직접 import, CLOVA Studio(HCX) 등 LLM 엔드포인트로 직접 HTTP 호출(`requests`/`httpx`/`aiohttp`), `src/llm` 밖에서의 자체 LLM 클라이언트 작성.
- 새 provider/모델이 필요하면 `src/llm` 안에 추가하고 `LlmCaller` 경유를 유지한다.
- 모델 호출 파라미터(provider/model/max_tokens/temperature)는 `src/llm/model_presets.py` 의 `ModelPreset` 에서만 가져온다(호출부 리터럴 금지). 상세는 `model-presets` 스킬.

## 테스트 규칙
- 테스트 시작·테스트 코드 작성·결과 저장 규칙(폴더/파일 네이밍, `_result.json`, `_report.md`): `test-convention` 스킬.