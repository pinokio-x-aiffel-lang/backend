# fake-news-detector
아이펠 엔지니어 1기 기업프로젝트


## Fast API 서버 띄우기
```bash
uv run uvicorn main:app --reload
```

브라우저 확인
```bash
http://127.0.0.1:8000/docs
```

요청 테스트
```bash
curl -X POST "http://127.0.0.1:8000/verify" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "통계청에 따르면 2024년 합계출산율은 0.72명이다."
  }'
```
