"""HCX native 모델(HCX-005/007/DASH-002): Function Calling/Structured Outputs/Thinking
중 2개 이상 동시 지정 시 호출 전에 LlmError로 차단되는지 확인.

가드는 provider 조회보다 먼저 실행되므로, 잘못된 model_alias를 넘기면
- 기능 충돌 시: 충돌 메시지로 LlmError (네트워크 호출 없음)
- 충돌 없을 시: provider 조회 단계의 "등록되지 않은 provider" LlmError
로 갈린다 → API 키/호출 불필요.

주의: json_structure는 HCX-005/DASH-002에서 별도 structured 가드가 먼저 막으므로,
상호배제(EXCL) 검증에는 json_mode/thinking/function_calling 조합만 사용한다.

대상 모듈: src.llm.llm_caller (기능 상호배제 가드)
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-05-26
"""
from src.llm.client import LlmError
from src.llm.llm_caller import LlmCaller

llm_caller = LlmCaller()

MODELS = ["HCX-005", "HCX-007", "HCX-DASH-002"]
MSG = [{"role": "user", "content": "테스트"}]

EXCL = "동시에 사용할 수 없습니다"
PROVIDER_ERR = "등록되지 않은 provider"


def _run(model_name: str, **kw) -> str:
    """chat() 호출 시 발생한 LlmError 메시지 반환 (API 호출 없음)."""
    try:
        llm_caller.chat(model_alias="__invalid__", model_name=model_name, messages=MSG, **kw)
    except LlmError as e:
        return str(e)
    return ""


# 기능 2개 이상 → 상호배제로 차단 기대
EXCL_CASES = {
    "FC + Thinking": dict(function_calling=True, thinking=True),
    "FC + json_mode": dict(function_calling=True, json_mode=True),
    "Thinking + json_mode": dict(thinking=True, json_mode=True),
    "FC + Thinking + json_mode": dict(function_calling=True, thinking=True, json_mode=True),
}
# 단일 기능 → 기능 가드 통과(이후 provider 조회에서 막힘) 기대
# (Thinking only는 HCX-007에서만 통과하므로 모델 공통 OK 케이스에서 제외)
OK_CASES = {
    "FC only": dict(function_calling=True),
    "none": dict(),
}

passed = failed = 0
for model in MODELS:
    print(f"\n{'='*70}\n  {model}\n{'='*70}")
    for label, kw in EXCL_CASES.items():
        msg = _run(model, **kw)
        ok = EXCL in msg
        print(f"  [{'✅' if ok else '❌'}] 차단 기대 | {label:28} | {msg or '(차단 안 됨)'}")
        passed += ok
        failed += not ok
    for label, kw in OK_CASES.items():
        msg = _run(model, **kw)
        ok = PROVIDER_ERR in msg
        print(f"  [{'✅' if ok else '❌'}] 통과 기대 | {label:28} | {'(기능 가드 통과)' if ok else msg}")
        passed += ok
        failed += not ok

print(f"\n{'='*70}\n  결과: {passed} passed, {failed} failed\n{'='*70}")
