# CLAUDE.md

## Git workflow
- When a task looks like new feature work, always ask "Should I create a new branch off `dev`?" before starting.
- Do not start the work until the user confirms, unless they explicitly say to continue on the current branch.
- Branch naming convention: suggest `feature/<short-description>`.
- When pushing to git, always push the current branch (`git push origin <current-branch>`). Never push directly to `main`, `master`, or `dev` unless the user explicitly asks.