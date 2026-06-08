"""한 claim의 후보 10개 표를 ①비동기 동시 ②순차로 조회 — N회 반복 측정.

①fetch_concurrent: aiohttp 네이티브 async + gather.
②fetch_sequential: requests 동기, for 루프, 파일 내 다른 함수 미사용(자체 구현).
매 회 결과를 result.json 에 기록하고, 종료 후 그 파일로 요약 표를 출력한다.
실행: uv run python benchmark/bench_concurrent_vs_sequential.py [--repeats N] [--claim "subject:pop:period:unit"]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import requests
from dotenv import load_dotenv

SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"
META_URL = "https://kosis.kr/openapi/statisticsData.do"  # getMeta
DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"  # getList

DEFAULT_CLAIM = ("총인구수", "전국", "2023", "명")  # subject, population, period, unit
_TOTAL_NAMES = {"계", "전체", "합계", "전국", "소계", "총계"}
RESULT_PATH = Path(__file__).resolve().parent / "result.json"


def _api_key() -> str:
    load_dotenv()
    key = os.getenv("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 없음 (.env 확인)")
    return key


async def _get(session, url, params) -> list[dict]:
    """KOSIS GET (format=json, jsonVD=Y) → list[dict]. err 응답이면 RuntimeError."""
    p = {"format": "json", "jsonVD": "Y", **params}
    async with session.get(url, params=p) as resp:
        resp.raise_for_status()
        data = json.loads(await resp.text())
    if isinstance(data, dict):
        if "err" in data or "errMsg" in data:
            raise RuntimeError(f"{data.get('err')}: {data.get('errMsg')}")
        return [data]
    return data if isinstance(data, list) else []


async def _search(session, key, keyword, top_n=10) -> list[tuple[str, str]]:
    rows = await _get(session, SEARCH_URL, {
        "method": "getList", "apiKey": key, "searchNm": keyword,
        "startCount": "1", "resultCount": str(top_n), "sort": "RANK",
    })
    return [(str(r.get("ORG_ID", "")), str(r.get("TBL_ID", ""))) for r in rows][:top_n]


def _norm(s) -> str:
    return "".join(str(s or "").split())


def _match_code(rows, target):
    t = _norm(target)
    if not t:
        return None
    for r in rows:
        if _norm(r.get("ITM_NM")) == t:
            return r.get("ITM_ID")
    cands = [r for r in rows if t in _norm(r.get("ITM_NM")) or _norm(r.get("ITM_NM")) in t]
    if cands:
        cands.sort(key=lambda r: len(_norm(r.get("ITM_NM"))))
        return cands[0].get("ITM_ID")
    return None


def _total_code(rows):
    for r in rows:
        if _norm(r.get("ITM_NM")) in _TOTAL_NAMES:
            return r.get("ITM_ID")
    return None


async def _query_one(session, key, org_id, tbl_id, subject, population, period):
    """후보 표 1개 조회 → (값|None, 사유|None). 성공이면 (float, None)."""
    try:
        itm = await _get(session, META_URL, {
            "method": "getMeta", "apiKey": key, "type": "ITM",
            "orgId": org_id, "tblId": tbl_id,
        })
    except (aiohttp.ClientError, RuntimeError, json.JSONDecodeError) as e:
        return None, f"메타 조회 실패({e})"

    items = [r for r in itm if isinstance(r, dict) and r.get("OBJ_ID") == "ITEM"]
    axes: dict[str, list] = {}
    for r in itm:
        if isinstance(r, dict) and r.get("OBJ_ID") and r["OBJ_ID"] != "ITEM":
            axes.setdefault(r["OBJ_ID"], []).append(r)

    itm_id = _match_code(items, subject)
    if itm_id is None:
        return None, f"항목 매칭 실패('{_norm(subject)}' 없음)"
    axis_ids = sorted(axes)
    if len(axis_ids) > 2:
        return None, f"분류축 {len(axis_ids)}개>2 미지원"
    codes = []
    for oid in axis_ids:
        c = _match_code(axes[oid], population) or _total_code(axes[oid])
        if c is None:
            return None, f"분류축 {oid} 매칭 실패('{_norm(population)}' 없음)"
        codes.append(c)

    try:
        rows = await _get(session, DATA_URL, {
            "method": "getList", "apiKey": key, "itmId": itm_id,
            "objL1": codes[0] if codes else "",
            "objL2": codes[1] if len(codes) > 1 else "",
            "objL3": "", "objL4": "", "objL5": "", "objL6": "", "objL7": "", "objL8": "",
            "prdSe": "Y", "startPrdDe": period, "endPrdDe": period,
            "orgId": org_id, "tblId": tbl_id,
        })
    except (aiohttp.ClientError, RuntimeError, json.JSONDecodeError) as e:
        return None, f"데이터 조회 실패({e})"

    match = {f"C{i + 1}": c for i, c in enumerate(codes)}
    for row in rows:
        if row.get("PRD_DE") == period and all(row.get(k) == v for k, v in match.items()):
            try:
                return float(row.get("DT")), None
            except (TypeError, ValueError):
                return None, f"DT 변환 실패({row.get('DT')!r})"
    return None, f"셀 0건(period={period} codes={codes or '없음'})"


async def _query_one_timed(session, key, org_id, tbl_id, subject, population, period):
    """_query_one + 표별 소요시간. (tbl_id, elapsed_s, value|None, reason|None) 반환."""
    t0 = time.perf_counter()
    val, reason = await _query_one(session, key, org_id, tbl_id, subject, population, period)
    return tbl_id, time.perf_counter() - t0, val, reason


def _summarize(tables: list[dict], wall: float) -> dict:
    return {
        "wall": round(wall, 3),
        "success": sum(t["ok"] for t in tables),
        "tables": tables,
    }


async def fetch_concurrent(session, key, cands, subject, population, period) -> dict:
    """① 비동기 동시 — 10개 표 동시 요청. 표별 시간·사유 담은 결과 dict 반환."""
    t0 = time.perf_counter()
    results = await asyncio.gather(*(
        _query_one_timed(session, key, org, tbl, subject, population, period)
        for org, tbl in cands
    ))
    wall = time.perf_counter() - t0
    tables = [
        {"tbl": tbl, "time": round(dt, 3), "ok": val is not None, "value": val, "reason": reason}
        for tbl, dt, val, reason in results
    ]
    return _summarize(tables, wall)


def fetch_sequential(key, cands, subject, population, period) -> dict:
    """② 동기식 순차 — requests로 한 표씩 요청→응답→다음. async·다른 함수 미사용.

    HTTP·이름매칭을 자체 구현. 표별 시간·사유 담은 결과 dict 반환.
    """
    meta_url = "https://kosis.kr/openapi/statisticsData.do"
    data_url = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    total_names = {"계", "전체", "합계", "전국", "소계", "총계"}
    sess = requests.Session()

    def get(url, params):
        r = sess.get(url, params={"format": "json", "jsonVD": "Y", **params}, timeout=20)
        r.raise_for_status()
        data = json.loads(r.text)
        if isinstance(data, dict):
            if "err" in data or "errMsg" in data:
                raise RuntimeError(f"{data.get('err')}: {data.get('errMsg')}")
            return [data]
        return data if isinstance(data, list) else []

    def norm(s):
        return "".join(str(s or "").split())

    def match_code(rows, target):
        t = norm(target)
        if not t:
            return None
        for r in rows:
            if norm(r.get("ITM_NM")) == t:
                return r.get("ITM_ID")
        c = [r for r in rows if t in norm(r.get("ITM_NM")) or norm(r.get("ITM_NM")) in t]
        if c:
            c.sort(key=lambda r: len(norm(r.get("ITM_NM"))))
            return c[0].get("ITM_ID")
        return None

    t0_all = time.perf_counter()
    tables = []
    for org_id, tbl_id in cands:
        t0 = time.perf_counter()
        val, reason = None, None
        try:
            itm = get(meta_url, {
                "method": "getMeta", "apiKey": key, "type": "ITM",
                "orgId": org_id, "tblId": tbl_id,
            })
            items = [r for r in itm if isinstance(r, dict) and r.get("OBJ_ID") == "ITEM"]
            axes = {}
            for r in itm:
                if isinstance(r, dict) and r.get("OBJ_ID") and r["OBJ_ID"] != "ITEM":
                    axes.setdefault(r["OBJ_ID"], []).append(r)

            itm_id = match_code(items, subject)
            axis_ids = sorted(axes)
            if itm_id is None:
                reason = f"항목 매칭 실패('{norm(subject)}' 없음)"
            elif len(axis_ids) > 2:
                reason = f"분류축 {len(axis_ids)}개>2 미지원"
            else:
                codes = []
                for oid in axis_ids:
                    rows_ax = axes[oid]
                    code = match_code(rows_ax, population)
                    if code is None:
                        for r in rows_ax:
                            if norm(r.get("ITM_NM")) in total_names:
                                code = r.get("ITM_ID")
                                break
                    if code is None:
                        reason = f"분류축 {oid} 매칭 실패('{norm(population)}' 없음)"
                        break
                    codes.append(code)
                else:  # 모든 축 매칭 성공 → 데이터 조회
                    data_rows = get(data_url, {
                        "method": "getList", "apiKey": key, "itmId": itm_id,
                        "objL1": codes[0] if codes else "",
                        "objL2": codes[1] if len(codes) > 1 else "",
                        "objL3": "", "objL4": "", "objL5": "",
                        "objL6": "", "objL7": "", "objL8": "",
                        "prdSe": "Y", "startPrdDe": period, "endPrdDe": period,
                        "orgId": org_id, "tblId": tbl_id,
                    })
                    mt = {f"C{i + 1}": c for i, c in enumerate(codes)}
                    for row in data_rows:
                        if row.get("PRD_DE") == period and all(row.get(k) == v for k, v in mt.items()):
                            try:
                                val = float(row.get("DT"))
                            except (TypeError, ValueError):
                                reason = f"DT 변환 실패({row.get('DT')!r})"
                            break
                    if val is None and reason is None:
                        reason = f"셀 0건(period={period} codes={codes or '없음'})"
        except (requests.RequestException, RuntimeError, json.JSONDecodeError) as e:
            reason = f"호출 실패({e})"

        dt = time.perf_counter() - t0
        tables.append({"tbl": tbl_id, "time": round(dt, 3), "ok": val is not None, "value": val, "reason": reason})

    wall = time.perf_counter() - t0_all
    return _summarize(tables, wall)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_table(path: Path) -> None:
    """result.json 을 읽어 10회 결과를 하나의 표로 출력."""
    data = json.loads(path.read_text(encoding="utf-8"))
    c = data["claim"]
    runs = data["runs"]
    n_tbl = len(data["candidates"])
    print(f"\n=== {len(runs)}회 결과 (claim={c['subject']}/{c['population']}/{c['period']}, 후보 {n_tbl}개) ===")
    print(f"{'run':>4} | {'동시(s)':>8} | {'순차(s)':>8} | {'배율':>6} | {'성공':>6}")
    print("-" * 46)
    cs, ss = [], []
    for r in runs:
        cw, sw = r["concurrent"]["wall"], r["sequential"]["wall"]
        cs.append(cw)
        ss.append(sw)
        ratio = sw / cw if cw else 0
        print(f"{r['run']:>4} | {cw:>8.2f} | {sw:>8.2f} | {ratio:>5.1f}x | {r['concurrent']['success']:>3}/{n_tbl}")
    print("-" * 46)
    ca, sa = sum(cs) / len(cs), sum(ss) / len(ss)
    print(f"{'평균':>4} | {ca:>8.2f} | {sa:>8.2f} | {sa / ca:>5.1f}x |")
    print(f"\n저장: {path}")


async def _run(spec: tuple[str, str, str, str], repeats: int) -> None:
    subject, population, period_raw, unit = spec
    period = re.sub(r"\D", "", period_raw)[:4]
    key = _api_key()
    data = {
        "claim": {"subject": subject, "population": population, "period": period_raw, "unit": unit},
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidates": [],
        "runs": [],
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        cands = await _search(s, key, subject, top_n=10)
        data["candidates"] = [t for _, t in cands]
        print(f"claim={subject}/{population}/{period_raw} | 후보 {len(cands)}개 | {repeats}회 반복")
        for i in range(1, repeats + 1):
            conc = await fetch_concurrent(s, key, cands, subject, population, period)
            seq = fetch_sequential(key, cands, subject, population, period)
            data["runs"].append({"run": i, "concurrent": conc, "sequential": seq})
            _write_json(RESULT_PATH, data)  # 매 회 기록(중간 중단 대비)
            print(f"  run {i:>2}/{repeats}: 동시 {conc['wall']:.2f}s | 순차 {seq['wall']:.2f}s | 성공 {conc['success']}/{len(cands)}")
    _print_table(RESULT_PATH)


def main() -> None:
    ap = argparse.ArgumentParser(description="표별 조회 — 동시 vs 순차, N회 반복 → result.json")
    ap.add_argument("--repeats", type=int, default=10, help="반복 횟수 (기본 10)")
    ap.add_argument(
        "--claim", type=lambda s: tuple(p.strip() for p in s.split(":")),
        default=DEFAULT_CLAIM, help="단일 claim 'subject:pop:period:unit'",
    )
    args = ap.parse_args()
    asyncio.run(_run(args.claim, args.repeats))


if __name__ == "__main__":
    main()
