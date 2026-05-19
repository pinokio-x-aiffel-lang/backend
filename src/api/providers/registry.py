"""provider 이름 → 인스턴스 매핑.

Provider 추가 시: 어댑터 1개 + 아래 딕셔너리에 1줄.
"""
from __future__ import annotations

from src.api.config import Settings
from src.api.providers.base import ChatProvider
from src.api.providers.hcx import HcxProvider

# provider 이름 → 실제 HCX 모델명
_HCX_MODELS_BY_NAME = {
    "hcx-dash-001": "HCX-DASH-001",
    "hcx-003": "HCX-003",
    "hcx-005": "HCX-005",
    "hcx-007": "HCX-007",
}


def build_registry(settings: Settings) -> dict[str, ChatProvider]:
    """기동 시 1회 호출. HCX 키가 없으면 호출자가 fail-fast 한다."""
    api_key = settings.clovastudio_api_key
    if not api_key:
        raise RuntimeError(
            "CLOVASTUDIO_API_KEY 가 주입되지 않음. "
            "`uv run x uvicorn ...`(infisical run) 으로 기동해야 한다."
        )

    registry: dict[str, ChatProvider] = {
        name: HcxProvider(
            api_key=api_key,
            model=model,
            timeout=settings.default_timeout_seconds,
        )
        for name, model in _HCX_MODELS_BY_NAME.items()
    }
    return registry
