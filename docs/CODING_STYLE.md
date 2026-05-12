# Coding Style (Python)

PEP 8 not repeated. Team rules only. Summary in `CLAUDE.md`.

## 1. Function Prefixes

| Prefix | Use |
|---|---|
| `fetch_` | External I/O |
| `get_` | In-memory lookup |
| `load_` | File/cache |
| `build_` | Construct |
| `parse_` | Parse |
| `extract_` | Subset |
| `validate_` | Raises |
| `is_`/`has_`/`should_` | Bool |
| `to_`/`from_` | Convert |

External calls must use `fetch_`.

## 2. Acronyms

Always lowercase, treated as one word.

```python
LlmClient, table_id, api_url   # OK
LLMClient, table_ID            # Bad
```

## 3. Collections

Singular vs plural, no type suffix. Dicts: `by_<key>`.

```python
claim, claims, claims_by_id    # OK
claims_list, claim_arr         # Bad
```

## 4. Directory Layout

```
src/
├── pipeline/
├── claim/
├── kosis/
├── numeric/
├── llm/
├── prompts/
├── schemas/
└── utils/
configs/
tests/
```

Split modules with multiple responsibilities. Names mirror the concept (`claim_extractor.py`).

## 5. Data Structures

### 5.1 Enums for States/Types

```python
class Verdict(str, Enum):
    TRUE = "T"; FALSE = "F"; NEEDS_REVIEW = "M"
```

`ClaimType` values: see §6.

### 5.2 Pipeline Artifacts

- Each stage returns a new artifact; no in-place mutation.
- New stage result → new artifact type.
- Validate external/LLM/API input at the boundary (Pydantic or explicit).

### 5.3 YAML Safety

Never `eval`/`exec`/shell/dynamic import on LLM YAML. Parse as declarative calc spec only.

## 6. Domain Vocabulary

| Identifier | Meaning |
|---|---|
| `claim` | Sentence under verification |
| `claim_card` | 8-field structured claim |
| `verdict` | T / F / M |
| `table_id` | KOSIS table id |
| `baseline` | Comparison statistic |
| `verifiable` | Mappable to stats |
| `mapping` | Claim → stats cell |
| `cascade` | Pre-filter → embedding → reranker → RAG |
| `ClaimType` | `absolute`, `change_rate`, `ratio`, `distribution`, `comparison`, `metaphoric` |

## 7. PR Checklist

- [ ] Prefixes per §1 (`get` vs `fetch`)
- [ ] Acronyms lowercase
- [ ] Collections plural, no `_list`/`_arr`
- [ ] No raw string literals for states/types
- [ ] New domain terms added to §6
