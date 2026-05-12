# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

This `code/` directory is currently **empty** — the project is in the pre-implementation / research-design phase. No build, lint, or test commands exist yet. When scaffolding begins, the agreed stack is Python 3.11+ with FastAPI (API), Streamlit (demo UI), SQLite (storage), FAISS or sqlite-vec (vectors), and pytest + a custom eval script for evaluation.

Planning documents (read these before doing substantive work) live in the **parent directory** `../`:
- `../1차제출_제안서.txt` — project proposal: problem definition, milestones, role split, evaluation metrics
- `../다이어그램_aain.txt` — the 9-step pipeline spec (claim detection → structuring → KOSIS retrieval → numeric comparison → verdict → explanation)
- `../refs/260506_claude_fact_check_poc_7week_plan.md` — the authoritative 7-week execution plan (architecture, sprints, decision gates, acceptance criteria)
- `../refs/260506_deep-research-report.md` — background research
- `../refs/슬롯스키마_예시_manual_verification_template.csv` — slot schema example
- `../data/[AI 기반 뉴스 사실검증 시스템] 프로젝트 데이터.csv` — Chosun Ilbo 2025 articles, columns: `기사제목, 작성일, URL, 기사 본문 전체, 검색 구분 레이블`
- `../(AI허브) 낚시성 기사 탐지 데이터/` — AI Hub clickbait-detection dataset (zipped)

## What this project actually is

Despite the name "가짜 뉴스 탐지" (fake news detection), the real scoped task is **numerical claim verification**: detect statistical/numeric claims in Korean news articles, structure them into slots, match them against official KOSIS statistics, recompute/compare the numbers, and emit a verdict (일치 / 불일치 / 판단불가) with a schema-constrained natural-language explanation. It's a 6–7 week PoC for a 3-person team, not a production service.

Critical data caveat: the `검색 구분 레이블` (True/False) in the article CSV only means "does the article cite 통계청/국가데이터처 keywords" — it does **not** mean the numbers are correct. Use True-labeled articles as gold-set candidates; never use this label directly as ground truth for verdict training/eval.

## Planned architecture (3 vertical modules + shared eval harness)

1. **Claim Module** — Claim Detection (5-class: 검증가능 / 단위정의 / 추정·전망 / 정성주장 / 비유비교), multi-claim decomposition, then Claim Normalization → JSON slots `{년도, 비교년도, 항목, 수치, 단위, 모집단, 집계방식, 인용출처}`.
2. **Evidence Module** — pre-curated KOSIS table catalog (~50–100 tables), 4-stage retrieval funnel (deterministic pre-filter → embedding Top-50 → reranker Top-5 → RAG-reasoning Top-1), then KOSIS API call + unit/period alignment. The LLM only *picks* a table; a deterministic adapter builds the actual KOSIS API params (KOSIS does **not** accept natural-language queries).
3. **Verdict & Service Module** — comparison logic with data-driven tolerance (significant-figure based, not a fixed ±1%), 3-class verdict, schema-constrained explanation, plus FastAPI `POST /verify` and Streamlit demo.
4. **Eval Harness** (shared) — gold-set evaluation + regression tests. Gold set is `(article, claim, answer)` triples, grows 50 → 200 over the project.

Core design principle running through every module: **the LLM never does arithmetic.** The LLM handles sentence structure / entailment / which-table-to-pick / how-to-compute (as a YAML/spec); a deterministic "Numeric Layer" performs all calculations. Explanations are slot-filled, not free-form, and every number/year/table-name in the explanation is regex-checked to be a subset of the structured inputs (hallucination guardrail) — regenerate on violation.

## Hard constraints to design around

- **KOSIS Open API: 1,000 calls/day** on a dev account. Build the catalog once, cache every `(orgId, tblId, period, classification)` call to disk (diskcache / lru_cache), use 통합검색 only for new matching.
- **LLM**: NCP HyperCLOVA X (HCX-DASH-002 for filtering, HCX-005/007 for normalization/verdict, RAG Reasoning for explanation), NCP Embedding v2, NCP Reranker. Korean-language models. All API keys via `.env` — never commit.
- **First major risk gate (Day 1–2)**: get one KOSIS table through API call → cell-value extraction end to end. This is the single biggest PoC risk.
- Prompts are code: keep all LLM prompts under version control; changes require an eval-set before/after comparison.
- Log every LLM call (input + output) as jsonl — error analysis depends on it.

## Working norms (from the 7-week plan)

- **Spec-first**: agree the module interface (input/output JSON schema, Pydantic models) before writing code. Interfaces freeze at Day 15.
- **Eval-driven**: any new feature must show its effect on the gold set before merge (regression guard).
- **Read before run**: this is a beginner team using coding agents — generated code must be read and understood before merging, not just executed.
- Decisions are grounded in primary sources + eval data, not intuition or trends.

## Conventions

Follow PEP 8 for Python (`python-convention` skill enforces this). Project-specific rules: see `docs/CODING_STYLE.md` before writing or modifying code.
