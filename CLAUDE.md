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