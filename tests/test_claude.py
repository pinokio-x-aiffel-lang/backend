from src.llm.llm_caller import LlmCaller
from src.llm.provider import CLAUDE_MODELS

llm_caller = LlmCaller()

models = CLAUDE_MODELS

for model_name in models:
    try:
        response = llm_caller.chat(
            model_alias="claude",
            model_name=model_name,
            messages=[{"role": "user", "content": "지금 미국 대통령은 누구지?"}],
            json_mode=True,
            max_tokens=4080,
        )
        print(f"[{model_name}] {response.text}")
        print(f"  tokens={response.total_tokens}, latency={response.latency_s:.2f}s")
        print("-" * 50)
    except Exception as e:
        print(f"[{model_name}] 실패: {e}")


for model_name in models:
    try:
        response = llm_caller.chat(
            model_alias="claude",
            model_name=model_name,
            messages=[{"role": "user", "content": "지금 미국 대통령은 누구지?"}],
            max_tokens=4080,
        )
        print(f"[{model_name}] {response.text}")
        print(f"  tokens={response.total_tokens}, latency={response.latency_s:.2f}s")
        print("-" * 50)
    except Exception as e:
        print(f"[{model_name}] 실패: {e}")
