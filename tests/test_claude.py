from src.llm.llm_caller import LlmCaller

# LLM 호출 모듈 인스턴스 생성
llm_caller = LlmCaller()  # .env 로딩

response = llm_caller.chat(
    model_alias="claude",  # provider.py에 등록된 alias
    model_name="claude-haiku-4-5-20251001",         # 실제 모델명
    messages=[{"role": "user", "content": "지금 미국 대통령은 누구지?"}],
    json_mode=True,
    max_tokens=4080,
)

print(response.text)
print(response.total_tokens, response.latency_s)
