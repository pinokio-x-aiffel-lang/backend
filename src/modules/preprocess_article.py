from __future__ import annotations

import asyncio
import json
import re

from langfuse import get_client

from src.llm.client import LlmError
from src.llm.model_presets import PREPROCESS
from src.observability.tracing import traced_chat
from src.prompts.prompts import PREPROCESS_ARTICLE_SYSTEM, PREPROCESS_ARTICLE_USER
from src.schemas.runtime import MasterSchema


# ── [1] 문서 정제 ─────────────────────────────────────────────────────────────

_RE_HTML_TAG     = re.compile(r"<[^>]+>")
_RE_HTML_ENTITY  = re.compile(r"&(?:amp|lt|gt|quot|nbsp|#\d+);")
_RE_EMAIL        = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
_RE_REPORTER     = re.compile(r"[가-힣]{2,4}\s*기자")
_RE_COPYRIGHT    = re.compile(r"[ⓒ©]\s*[\w가-힣\s]+|무단\s*전재[^.]*|재배포\s*금지[^.]*")
_RE_DECORATIVE   = re.compile(r"[◆■▶◀●◇□△▽★☆※→←↑↓【】]")
_RE_MULTI_SPACE  = re.compile(r"[ \t]+")
_RE_MULTI_NL     = re.compile(r"\n{3,}")


def _clean_document(text: str) -> str:
    text = _RE_HTML_TAG.sub(" ", text)
    text = _RE_HTML_ENTITY.sub(" ", text)
    text = _RE_EMAIL.sub("", text)
    text = _RE_REPORTER.sub("", text)
    text = _RE_COPYRIGHT.sub("", text)
    text = _RE_DECORATIVE.sub("", text)
    text = _RE_MULTI_SPACE.sub(" ", text)
    text = _RE_MULTI_NL.sub("\n\n", text)
    return text.strip()


# ── [2] 문장 분리 ─────────────────────────────────────────────────────────────

# 한글·숫자·% 뒤의 마침표 + 공백 + 한글 시작 → 분리 (소수점·날짜 제외)
_RE_INTRA_SENT = re.compile(r'(?<=[가-힣%\d\)])\.\s+(?=[가-힣])')


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 6:
            continue
        parts = _RE_INTRA_SENT.split(line)
        sentences.extend(p.strip() for p in parts if len(p.strip()) >= 6)
    return sentences


# ── [3] 원자 문장화 (HCX-005) ─────────────────────────────────────────────────

def _fmt_numbered(sentences: list[str]) -> str:
    return "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))


async def _atomize_batch(sentences: list[str]) -> list[str]:
    messages = [
        {"role": "system", "content": PREPROCESS_ARTICLE_SYSTEM},
        {"role": "user", "content": PREPROCESS_ARTICLE_USER.format(
            numbered_sentences=_fmt_numbered(sentences)
        )},
    ]
    try:
        response = await asyncio.to_thread(
            traced_chat,
            model_alias=PREPROCESS.model_alias,
            model_name=PREPROCESS.model_name,
            messages=messages,
            max_tokens=PREPROCESS.max_tokens,
            trace_name="preprocess:atomize",
            prompt_name="preprocess_article",
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(text)
        result = [s.strip() for s in data.get("sentences", []) if s.strip()]
        return result if result else sentences
    except (LlmError, json.JSONDecodeError, AttributeError):
        return sentences  # 실패 시 원문 그대로


async def _atomize_all(sentences: list[str]) -> list[str]:
    # 20개씩 배치 (토큰 한도 방어)
    batch_size = 20
    batches = [sentences[i:i + batch_size] for i in range(0, len(sentences), batch_size)]
    results = await asyncio.gather(*[_atomize_batch(b) for b in batches])
    return [s for group in results for s in group]


# ── [4] 문장 정제 ─────────────────────────────────────────────────────────────

_RE_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.!?])")
_RE_MISSING_PERIOD     = re.compile(r"([가-힣])\s*$")


def _clean_sentences(sentences: list[str]) -> list[str]:
    cleaned: list[str] = []
    for s in sentences:
        s = s.strip()
        s = _RE_SPACE_BEFORE_PUNCT.sub(r"\1", s)  # "이다 ." → "이다."
        s = _RE_MISSING_PERIOD.sub(r"\1.", s)      # 마침표 누락 시 추가
        if len(s) > 5:
            cleaned.append(s)
    return cleaned


# ── 공개 API ─────────────────────────────────────────────────────────────────

def clean_and_split(content: str) -> list[str]:
    """[1] 문서 정제 + [2] 문장 분리 (규칙 기반, LLM 미사용)."""
    return _split_sentences(_clean_document(content))


async def atomize_sentences(sentences: list[str]) -> list[str]:
    """[3] 원자 문장화 (HCX-005) + [4] 문장 정제."""
    return _clean_sentences(await _atomize_all(sentences))


# ── 엔트리포인트 ──────────────────────────────────────────────────────────────

class PreprocessArticleError(Exception):
    """기사 전처리 실패."""


async def preprocess_article(master_schema: MasterSchema) -> None:
    """
    [2] Preprocess Article

    Input:  master_schema.article.content
    Output: master_schema.sentences  (list[str], 검증 단위 원자 문장)

    내부 단계:
      [1] 문서 정제   — 기사 전체 노이즈 제거 (규칙 기반)
      [2] 문장 분리   — 정제된 텍스트를 문장 단위로 분리 (규칙 기반)
      [3] 원자 문장화 — 복합 문장 → 검증 가능한 단위 문장 (HCX-005)
      [4] 문장 정제   — LLM 출력 포맷 정규화 (규칙 기반)
    """
    if not master_schema.article:
        raise PreprocessArticleError("master_schema.article 이 없습니다.")

    lf = get_client()
    content = master_schema.article.content

    with lf.start_as_current_observation(
        as_type="span",
        name="preprocess_article",
        input={"article_id": master_schema.article.article_id, "content_length": len(content)},
    ) as root:

        with lf.start_as_current_observation(as_type="span", name="[1] 문서정제") as s:
            cleaned_doc = _clean_document(content)
            s.update(output={
                "before": len(content),
                "after": len(cleaned_doc),
                "removed": len(content) - len(cleaned_doc),
            })

        with lf.start_as_current_observation(as_type="span", name="[2] 문장분리") as s:
            raw_sentences = _split_sentences(cleaned_doc)
            if not raw_sentences:
                raise PreprocessArticleError("문장 분리 결과가 없습니다.")
            s.update(output={"n_sentences": len(raw_sentences), "sentences": raw_sentences})

        # [3] 원자 문장화 — traced_chat 이 내부에서 generation 으로 기록
        atomic_sentences = await _atomize_all(raw_sentences)

        with lf.start_as_current_observation(as_type="span", name="[4] 문장정제") as s:
            final = _clean_sentences(atomic_sentences)
            s.update(output={"n_sentences": len(final), "sentences": final})

        root.update(output={"n_sentences": len(final)})

    master_schema.sentences = final
