---
name: model-presets
description: Use when writing or changing any LLM call (LlmCaller.chat) — picking a model or setting max_tokens/temperature. Params must come from a ModelPreset in src/llm/model_presets.py, not literals.
---

# Model Presets

Model/step not covered? Add a `ModelPreset` constant in `src/llm/model_presets.py`.

```python
from src.llm.model_presets import EXTRACT_CLAIMS as P

_llm.chat(P.model_alias, P.model_name, messages,
          max_tokens=P.max_tokens, temperature=P.temperature)
```
