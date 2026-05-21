# infisical 사용을 uv run x ~~ 이런식으로 적용할 수 있게 만들어줌
import subprocess, sys

def main():
    sys.exit(subprocess.call(
        ["infisical", "run", "--", "uv", "run", *sys.argv[1:]]
    ))
