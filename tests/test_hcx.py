from src.llm.llm_caller import LlmCaller

# LLM 호출 모듈 인스턴스 생성
llm_caller = LlmCaller()  # .env 로딩

schema = {
        "type": "object",
        "properties": {
          "이름": {
            "type": "string",
            "description": "Person's name"
          },
          "국적": {
            "type": "string",
            "description": "Person's nationality"
          }
        },
        "required": [
          "이름",
          "국적"
        ]
    }

for i in range(3):
    response = llm_caller.chat(
        model_alias="hyperclova",  # provider.py에 등록된 alias
        model_name="HCX-007",         # 실제 모델명
        messages=[{"role": "user", "content": "지금 미국 대통령은 누구지?"}],
        json_mode=True,
        json_structure=schema,
        max_tokens=4080,
    )

    print(response.text)
    print(response.total_tokens, response.latency_s)
    print("---")