#!/usr/bin/env bash
input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // ""')

# Skip if not a git push
echo "$command" | grep -qE '(^|[;&|])\s*git\s+push' || exit 0

current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

# Block explicit push to main/master
if echo "$command" | grep -qE 'git\s+push\s+\S+\s+(\S+:)?(main|master)\b'; then
  echo "BLOCKED: Pushing to main/master is not allowed. Push the current branch instead: git push origin ${current_branch}" >&2
  exit 2
fi

# Block any push while on main/master
if [[ "$current_branch" == "main" || "$current_branch" == "master" ]]; then
  echo "BLOCKED: You are on '${current_branch}'. Create a feature branch before pushing." >&2
  exit 2
fi

exit 0