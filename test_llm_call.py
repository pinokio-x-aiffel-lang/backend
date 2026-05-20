from src.llm.router import LlmRouter

router = LlmRouter()  # .env 자동 로딩

response = router.chat(
    model_alias="claim-detection-gemini",  # provider.py에 등록된 alias
    model_name="gemini-2.5-flash",         # 실제 모델명
    messages=[{"role": "user", "content": "지금 미국 대통령은 누구지?"}],
    max_tokens=4080,
)

print(response.text)
print(response.total_tokens, response.latency_s)
