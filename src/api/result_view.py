"""result.md(파이프라인 단계별 기록) → JSON 파싱.

GET /result(루트 main.py)가 이걸 써서 result.md 를 보기 좋은 JSON 으로 반환한다.
result.md 형식(src/pipeline/result_md.py 가 기록):
    # <제목>
    ## <번호>. <단계명>
    - **<점표기 경로>**: <값>      ← 단계가 채운/바꾼 부분
    ### ...                        ← 5단계만 붙는 사람용 상세(마크다운 그대로 보존)
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from src.pipeline.result_md import DEFAULT_RESULT_PATH

# 파이프라인이 기록하는 파일과 동일 경로(단일 출처).
RESULT_PATH = DEFAULT_RESULT_PATH

_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")
_HEADER_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^-\s+\*\*(.+?)\*\*:\s?(.*)$")


class ResultStep(BaseModel):
    step: int
    name: str
    changes: dict[str, str]
    detail: str | None = None  # 5단계 등 '### ' 이하 상세(마크다운 원문)


class ResultResponse(BaseModel):
    title: str
    steps: list[ResultStep]


def parse_result_md(text: str) -> dict:
    """result.md 마크다운 → {title, steps:[{step, name, changes, detail?}]}."""
    title = ""
    steps: list[dict] = []
    current: dict | None = None
    detail: list[str] | None = None  # '### ' 만나면 그 이후를 여기에 수집

    def flush() -> None:
        if current is None:
            return
        if detail is not None:
            current["detail"] = "\n".join(detail).strip("\n")
        steps.append(current)

    for line in text.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            flush()
            current = {"step": int(header.group(1)), "name": header.group(2), "changes": {}}
            detail = None
            continue
        if current is None:  # 첫 단계 전: 제목만 줍는다
            tm = _TITLE_RE.match(line)
            if tm and not title:
                title = tm.group(1)
            continue
        if detail is not None:  # 상세 수집 중이면 그대로 누적
            detail.append(line)
            continue
        if line.startswith("### "):
            detail = [line]
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            current["changes"][bullet.group(1)] = bullet.group(2)

    flush()
    return {"title": title, "steps": steps}
