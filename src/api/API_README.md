# 호출할 수 잇는 구문

- 서버 띄운 뒤 다른 터미널에서 호출하면 됩니다. 

  1) 서버 기동 (이 터미널은 서버가 점유함)

  uv run x uvicorn src.api.chat_app:app --host 0.0.0.0 --port 8000
  # 또는
  bash src/api/run.sh

  Uvicorn running on http://0.0.0.0:8000 가 뜨면 준비 완료.

  2) 호출 (새 터미널에서)

  # liveness
  curl http://localhost:8000/health

  # provider 목록
  curl http://localhost:8000/v1/providers

  # 단일 turn
  curl -X POST http://localhost:8000/v1/chat \
    -H "Content-Type: application/json" \
    -d '{"provider": "hcx-005", "messages": [{"role": "user", "content": "2024년 합계출산율은?"}]}'

  # 멀티 turn (system + 이전 대화 포함, stateless 라 매번 전체 전송)
  curl -X POST http://localhost:8000/v1/chat \
    -H "Content-Type: application/json" \
    -d '{

  2) 호출 (새 터미널에서)

  # liveness
  curl http://localhost:8000/health

  # provider 목록
  curl http://localhost:8000/v1/providers

  # 단일 turn
  curl -X POST http://localhost:8000/v1/chat \
    -H "Content-Type: application/json" \
    -d '{"provider": "hcx-005", "messages": [{"role": "user", "content": "2024년 합계출산율은?"}]}'

  # 멀티 turn (system + 이전 대화 포함, stateless 라 매번 전체 전송)
  curl -X POST http://localhost:8000/v1/chat \
    -H "Content-Type: application/json" \
    -d '{
      "provider": "hcx-005",

  # provider 목록
  curl http://localhost:8000/v1/providers

  # 단일 turn
  curl -X POST http://localhost:8000/v1/chat \
    -H "Content-Type: application/json" \
    -d '{"provider": "hcx-005", "messages": [{"role": "user", "content": "2024년 합계출산율은?"}]}'

  # 멀티 turn (system + 이전 대화 포함, stateless 라 매번 전체 전송)
  curl -X POST http://localhost:8000/v1/chat \
    -H "Content-Type: application/json" \
    -d '{
      "provider": "hcx-005",
      "messages": [
        {"role": "system", "content": "당신은 팩트체크 어시스턴트입니다."},
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "안녕하세요!"},
        {"role": "user", "content": "방금 내가 뭐라고 했지?"}
      ],
      "temperature": 0.3,
      "max_tokens": 512
    }'

  브라우저로 테스트하려면 http://localhost:8000/docs (Swagger UI)에서 바로 호출할 수도 있습니다.

  참고:
  - provider 가능값: hcx-dash-001, hcx-003, hcx-005, hcx-007
  - 이 채팅에서 제가 직접 켜서 호출하길 원하시면, 위 1)을 제가 백그라운드로 실행하고 결과를 보여드릴 수도 있습니다. 직접 해보실 거면 터미널 입력창에 ! 를 붙여 !uv run
  x uvicorn src.api.chat_app:app --port 8000 처럼 실행하면 출력이 이 세션에 그대로 들어옵니다.

✻ Cooked for 13s

※ recap: Built a FastAPI server in src/api/ wrapping the existing LLM client, with Infisical CLI key injection verified working. It's complete and tested. Next: you
  run `uv run x uvicorn src.api.chat_app:app --port 8000` from the project root and call it via the curl commands provided.
      "max_tokens": 512
    }'

  브라우저로 테스트하려면 http://localhost:8000/docs (Swagger UI)에서 바로 호출할 수도 있습니다.

  참고:
  - provider 가능값: hcx-dash-001, hcx-003, hcx-005, hcx-007
  - 이 채팅에서 제가 직접 켜서 호출하길 원하시면, 위 1)을 제가 백그라운드로 실행하고 결과를 보여드릴 수도 있습니다. 직접 해보실 거면 터미널
  입력창에 ! 를 붙여 !uv run x uvicorn src.api.chat_app:app --port 8000 처럼 실행하면 출력이 이 세션에 그대로 들어옵니다.

✻ Cooked for 13s

※ recap: Built a FastAPI server in src/api/ wrapping the existing LLM client, with Infisical CLI key injection verifieworking. It's complete
   and tested. Next: you run `uv run x uvicorn src.api.chat_app:app --port 8000` from the project root and call it via thecurl commands provided.

  브라우저로 테스트하려면 http://localhost:8000/docs (Swagger UI)에서 바로 호출할 수도 있습니다.

  참고:
  - provider 가능값: hcx-dash-001, hcx-003, hcx-005, hcx-007
  - 이 채팅에서 제가 직접 켜서 호출하길 원하시면, 위 1)을 제가 백그라운드로 실행하고 결과를 보여드릴 수도 있습니다.

  참고:
  - provider 가능값: hcx-dash-001, hcx-003, hcx-005, hcx-007
  - 이 채팅에서 제가 직접 켜서 호출하길 원하시면, 위 1)을 제가 백그라운드로 실행하고 결과를 보여드릴 수도 있습니다.
  직접 해보실 거면 터미널 입력창에 ! 를 붙여 !uv run x uvicorn src.api.chat_app:app --port 8000 처럼 실행하면 출력이 이
  세션에 그대로 들어옵니다.

✻ Cooked for 13s

※ recap: Built a FastAPI server in src/api/ wrapping the existing LLM client, with Infisical CLI key injection verified
   working. It's complete and tested. Next: you run `uv run x uvicorn src.api.chat_app:app --port 8000` from the project
  root and call it via the curl commands provided. (disable recaps in /config)

❯ 8000으로 접근하니까 안되는데? port번호랑 접속 주소 다시 확인해봐.                                                    

⏺ Bash(echo "=== 8000 리슨 중인가 ===" ; lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null || echo "8000 에 리슨 중인
      프로세스 없음 (서버가 안 떠있음)" ; echo ; echo "=== uvicorn / infisical 관련 프…)
  ⎿  === 8000 리슨 중인가 ===
     8000 에 리슨 중인 프로세스 없음 (서버가 안 떠있음)
     … +2 lines (ctrl+o to expand)

⏺ 포트·주소 문제가 아니라 서버가 안 떠 있어서 그렇습니다. 앞서 스모크 테스트용 서버(8077/8079)는 모두 종료했고,
  8000번에 떠 있는 프로세스가 없습니다. 직접 호출하실 수 있게 제가 8000번으로 띄워두겠습니다.

⏺ Bash(cd /Users/leeaain/project/pinokio-x/fake_news_detect && (bash src/api/run.sh > /tmp/api_8000.log 2>&1 &) ; for i
       in $(seq 1 30); do curl -s -o /dev/null -w "%{h…)
  ⎿  Waiting…