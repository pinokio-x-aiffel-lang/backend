"""result.md 기록 — MasterSchema 단계별 델타를 사람이 보는 마크다운으로 적는다.

make_result_recorder() 가 Pipeline.run(on_step=...) 에 넘길 콜백을 만든다.
runner.py(CLI 실행)와 verify_service(서버 요청)가 이 콜백을 공유해 같은 파일을 쓴다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.schemas.runtime import MasterSchema

# 프로젝트 루트/tests/result.md (이 파일은 src/pipeline/ 아래 → parents[2] = 루트)
DEFAULT_RESULT_PATH = Path(__file__).resolve().parents[2] / "tests" / "result.md"

_MISSING = object()


def _flatten(value, prefix: str = "") -> dict:
    """MasterSchema model_dump → {점표기 경로: 스칼라} 평탄화."""
    out: dict = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = value
    return out


def _delta_md(old_flat: dict, new_flat: dict) -> str:
    """직전 스냅샷 대비 추가/변경된 경로만 마크다운 불릿으로 — '그 단계가 채운 부분'."""
    lines: list[str] = []
    for path, new_val in new_flat.items():
        old_val = old_flat.get(path, _MISSING)
        if old_val is _MISSING:
            lines.append(f"- **{path}**: {new_val}")
        elif old_val != new_val:
            lines.append(f"- **{path}**: {old_val} → {new_val}")
    return "\n".join(lines) if lines else "_(변경 없음)_"


def _format_step5_detail(ms: MasterSchema) -> str:
    """5단계(KOSIS 셀 조회) 디버깅 상세 — 실제 데이터 그대로 표시.

    claim 추출값(원문 그대로, 띄어쓰기 포함) / KOSIS 에 넣은 값 / 후보 표별 항목·분류축·
    매칭 사유(왜 못 찾았는지) / 목표 셀 좌표 / 얻어낸 cell 값.
    master_schema(claims·analysis.cell_attempts·kosis_query·evidence)만으로 구성한다.
    """
    claims = {c.claim_id: c for c in ms.claims}
    out: list[str] = ["", "### 📊 5단계 상세 — claim 추출값 · 검색값 · 후보 표 디버깅", ""]
    for a in ms.analysis:
        c = claims.get(a.claim_id)
        if c is None:
            continue
        ev = a.evidence
        matched = ev is not None and ev.value is not None

        out.append(f"**[{a.claim_id}] {c.subject}**")
        # ① claim 추출값 — 추출된 그대로(띄어쓰기 포함). 값들은 | 로 구분
        out.append(
            f"- 📌 claim 추출값: "
            f"값 `{c.value.llm_value}`(원문 `{c.value.raw}`) "
            f"| 시점 `{c.period_value.llm_value}`(원문 `{c.period_value.raw}`) "
            f"| 모집단 `{c.population}` | 단위 `{c.unit}` | subject `{c.subject}`"
        )
        # ② KOSIS 에 실제로 넣은 값 (검색어는 공백 제거 형태)
        out.append(
            f"- 🔍 KOSIS 에 넣은 값: subject `{''.join(c.subject.split())}`(공백 제거) "
            f"| population `{c.population}` | period `{c.period_value.llm_value}`"
        )
        # ③ 후보 표별 조회 시도 — 항목·분류축·매칭 사유(왜 못 찾았는지)
        out.append(f"- 📑 후보 표별 조회 시도 {len(a.cell_attempts)}개:")
        for att in a.cell_attempts:
            star = " ★채택" if att.matched else ""
            out.append(f"    - `{att.tbl_id}` {att.tbl_nm}{star}")
            if att.error and att.error.startswith("스킵"):
                out.append(f"        - {att.error}")
                continue
            if att.items:
                out.append(f"        - 항목: {', '.join(att.items)}")
            for ax, vals in att.axes.items():
                out.append(f"        - 분류축 [{ax}]: {', '.join(vals)}")
            if att.matched:
                out.append(f"        - 결과: ✅ {att.value} {att.unit} (itmId {att.itm_id})")
            else:
                out.append(f"        - 결과: ❌ {att.error}")
        # ④ 목표 셀 좌표(찾으려는 것) + 얻어낸 값
        if matched:
            if a.kosis_query and a.kosis_query.params:
                out.append(f"- 🎯 얻으려는 셀 좌표: `{a.kosis_query.params}`")
            out.append(
                f"- 🎯 얻어낸 cell 값: **{ev.value} {ev.unit}** | 시점 {ev.period} "
                f"| 표 `{ev.kosis_tbl_id}` | itmId {ev.kosis_item_id}"
            )
        else:
            err = a.kosis_query.error_msg if a.kosis_query else "(조회 안 됨)"
            out.append(f"- 🎯 얻어낸 cell 값: ❌ 없음 — {err}")
        out.append("")
    return "\n".join(out)


def make_result_recorder(
    content: str, result_path: Path | None = None
) -> Callable[[int, str, MasterSchema], None]:
    """단계별 델타를 result_path(기본 tests/result.md)에 기록하는 on_step 콜백 생성.

    호출 즉시 파일을 헤더로 초기화(덮어쓰기)하고, 시작 스냅샷(전부 비어 있음) 대비
    각 단계가 채운 델타만 append 한다. 반환값을 Pipeline.run(on_step=...) 에 넘긴다.
    """
    path = result_path or DEFAULT_RESULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# 단계별 기록 (각 단계가 채운 부분)\n", encoding="utf-8")

    prev = _flatten(MasterSchema(content=content).model_dump(by_alias=False))

    def record(step: int, name: str, ms: MasterSchema) -> None:
        nonlocal prev
        curr = _flatten(ms.model_dump(by_alias=False))
        section = f"\n## {step}. {name}\n\n{_delta_md(prev, curr)}\n"
        if step == 5:  # 5단계는 사람이 보기 좋은 요약을 하단에 덧붙인다
            section += _format_step5_detail(ms) + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(section)
        prev = curr

    return record
