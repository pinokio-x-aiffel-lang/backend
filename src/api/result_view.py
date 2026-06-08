"""result.md(파이프라인 단계별 기록) → JSON 파싱.

GET /result(루트 main.py)가 이걸 써서 result.md 를 보기 좋은 JSON 으로 반환한다.
result.md 형식(src/pipeline/result_md.py 가 기록):
    # <제목>
    ## <번호>. <단계명>
    - **<점표기 경로>**: <값>      ← 단계가 채운/바꾼 부분
    ### ...                        ← 5단계만 붙는 사람용 상세(마크다운 그대로 보존)
"""
from __future__ import annotations

import json
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


# ── 사람용 HTML 뷰 ───────────────────────────────────────────────────────────
# result.md(마크다운)를 브라우저에서 서식대로 렌더한다. 서버에 마크다운 라이브러리가
# 없으므로 marked.js(CDN)로 클라이언트 렌더. 마크다운 원문은 페이지에 그대로 임베드.

_VIEW_HEAD = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>검증 결과 — result.md</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  body { max-width: 920px; margin: 2rem auto; padding: 0 1.2rem;
         font-family: -apple-system, "Apple SD Gothic Neo", "Segoe UI", system-ui, sans-serif;
         line-height: 1.65; color: #1f2328; }
  h1 { font-size: 1.7rem; border-bottom: 2px solid #d0d7de; padding-bottom: .3rem; }
  h2 { font-size: 1.3rem; margin-top: 2rem; border-bottom: 1px solid #d0d7de; padding-bottom: .25rem; }
  h3 { font-size: 1.1rem; margin-top: 1.4rem; }
  ul { padding-left: 1.4rem; }
  li { margin: .15rem 0; }
  code { background: #f0f2f4; padding: .12em .35em; border-radius: 5px;
         font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em; }
  pre { background: #f6f8fa; padding: 1rem; border-radius: 8px; overflow: auto; }
  pre code { background: none; padding: 0; }
  strong { color: #0b3d91; }
  table { border-collapse: collapse; } th, td { border: 1px solid #d0d7de; padding: .4rem .6rem; }
</style>
</head>
<body>
<article id="content"></article>
<script>
const md = """

_VIEW_TAIL = """;
document.getElementById("content").innerHTML = marked.parse(md);
</script>
</body>
</html>"""


def render_result_html(md_text: str) -> str:
    """result.md 마크다운 → marked.js 로 렌더하는 자체 완결 HTML 페이지.

    md_text 를 JS 문자열 리터럴로 안전 임베드(JSON 인코딩 + '<'→'\\u003c' 로
    '</script>' 조기 종료 방지)한 뒤, 브라우저에서 marked.parse 로 서식 렌더한다.
    """
    md_js = json.dumps(md_text).replace("<", "\\u003c")
    return _VIEW_HEAD + md_js + _VIEW_TAIL
