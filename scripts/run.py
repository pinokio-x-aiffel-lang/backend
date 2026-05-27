# infisical 사용을 uv run x ~~ 이런식으로 적용할 수 있게 만들어줌
import subprocess, sys
"""
langfuse도 여기에 함께 넣기.
infisical run --env dev --path / --path /LangFuse -- uv run python <스크립트>
""" 

def main():
    sys.exit(subprocess.call(
        ["infisical", "run", "--", "uv", "run", *sys.argv[1:]]
    ))
