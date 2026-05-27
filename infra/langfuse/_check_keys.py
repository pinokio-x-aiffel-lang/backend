"""LANGFUSE_* 환경변수의 ASCII 유효성만 점검 (값 자체는 출력하지 않음)."""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

for k in ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"]:
    v = os.environ.get(k)
    if v is None:
        print(f"{k}: (없음)")
        continue
    try:
        v.encode("ascii")
        print(f"{k}: len={len(v)} ascii=OK  prefix={v[:6]!r}")
    except UnicodeEncodeError as e:
        bad = e.start
        print(
            f"{k}: len={len(v)} ascii=BAD  bad_pos={bad} "
            f"bad_char={v[bad]!r}  prefix={v[:6]!r}"
        )
