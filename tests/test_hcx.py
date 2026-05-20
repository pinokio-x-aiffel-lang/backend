from src.llm.llm_caller import LlmCaller
from src.llm.provider import HCX_MODEL_INFO, HCX_MODELS

# LLM 호출 모듈 인스턴스 생성
llm_caller = LlmCaller()  # .env 로딩

models = HCX_MODELS

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

for model_name in models:
    print(f"\n{'='*50}")
    print(f"  모델: {model_name}")
    print(f"{'='*50}")
    try:
        info = HCX_MODEL_INFO[model_name]
        # context_window가 병목인 모델(HCX-DASH-001)을 위해 출력 한도를 context_window의 절반으로 제한
        safe_max = min(info["max_output_tokens"], info["context_window"] // 2)
        response = llm_caller.chat(
            model_alias="hyperclova",
            model_name=model_name,
            messages=[{"role": "user", "content": "지금 미국 대통령은 누구지?"}],
            json_structure=schema if model_name == HCX_MODELS[0] else None,
            max_tokens=safe_max,
        )
        print(f"  응답: {response.text}")
        print(f"  tokens={response.total_tokens}, latency={response.latency_s:.2f}s")
    except Exception as e:
        print(f"  실패: {e}")