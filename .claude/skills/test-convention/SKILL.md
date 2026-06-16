---
name: test-convention
description: Use whenever starting a new test, writing test code, or saving test results. Enforces where test files live (a per-test folder under benchmark/), the folder/file naming, the raw-result JSON, and the readable report MD.
---

# Test Convention

## Folder

Every new test gets its own folder under `benchmark/`:

```
benchmark/<YYMMDD>_<stage>_<topic>_<authorId>/
```

- `<stage>` — pipeline step(s) per `src/pipeline/runner.py` (10 steps). Range with `~`.
- Example: `benchmark/260616_2~5_pipeline_leeaain/`

All files for that test live inside this folder and share its name as the base.

## Files

| File | Content |
| --- | --- |
| `<folder>.py` | Test code. Same base name as the folder. |
| `<folder>_result.json` | Raw test output, verbatim. |
| `<folder>_report.md` | Human-readable report. |

### `_result.json` — raw output (for debugging)

Dump the actual schema produced by the test, unmodified. Include **only the keys/values that the test transformed or added** (the diff), not the full untouched input.

### `_report.md` — readable report

Cover, in this order, formatted for readability:
1. Overview — purpose of the test.
2. What was tested.
3. Metric results.
