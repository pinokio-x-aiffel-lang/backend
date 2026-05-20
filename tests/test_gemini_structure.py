from src.llm.llm_caller import LlmCaller

# LLM 호출 모듈 인스턴스 생성
llm_caller = LlmCaller()  # .env 로딩


schema = {
    "name": "claim",
    "schema": {
        "type": "object",
        "properties": {
            "년도": {"type": "string"},
            "인종": {"type": "string"},
            "이름": {"type": "string"}
        },
        "required": ["년도", "이름"],
    }
}

response = llm_caller.chat(
    model_alias="gemini",  # provider.py에 등록된 alias
    model_name="gemini-3.5-flash",         # 실제 모델명
    messages=[{"role": "user", "content": "지금 미국 대통령은 누구지?"}],
    json_mode=True,
    json_structure=schema,
    max_tokens=4080,
)

print(response.text)
print(response.total_tokens, response.latency_s)
