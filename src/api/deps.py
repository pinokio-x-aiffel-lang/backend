"""의존성 주입.

registry / logger 는 기동 시 1회 만들어 app.state 에 둔다(요청마다 재생성 X).
provider 선택은 요청 body 의 provider 이름으로 라우터에서 수행한다.
"""
from __future__ import annotations

from fastapi import Request

from src.api.logging_utils import JsonlLogger
from src.api.providers.base import ChatProvider


def get_registry(request: Request) -> dict[str, ChatProvider]:
    return request.app.state.registry


def get_logger(request: Request) -> JsonlLogger:
    return request.app.state.logger
