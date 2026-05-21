"""JSONL 요청·응답 로깅 + 시크릿 마스킹.

평가셋 구축·재현성을 위해 요청/응답 전문을 한 줄 JSON 으로 남긴다.
시크릿 값이 절대 파일에 찍히지 않도록 마스킹한다.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# nv- 로 시작하는 NCP 키, 그 외 흔한 시크릿 키 이름을 마스킹
_KEY_VALUE_RE = re.compile(r"\bnv-[A-Za-z0-9]{8,}\b")
_SECRET_KEY_NAMES = {
    "api_key",
    "apikey",
    "clovastudio_api_key",
    "hcx_api_key",
    "authorization",
    "infisical_client_secret",
}


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        return _KEY_VALUE_RE.sub("***", value)
    if isinstance(value, dict):
        return {
            k: ("***" if k.lower() in _SECRET_KEY_NAMES else _mask(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask(v) for v in value]
    return value


class JsonlLogger:
    """append-only JSONL 로거. 날짜별 파일."""

    def __init__(self, log_dir: str) -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def log(self, record: dict[str, Any]) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._dir / f"chat-{day}.jsonl"
        safe = _mask(record)
        safe["ts"] = datetime.now(timezone.utc).isoformat()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
