---
name: git-convention
description: Use this skill whenever the user asks to create commits, write commit messages, create branches, open pull requests, or merge branches. Enforces this project's branch strategy (main/develop with feat/fix/chore/exp working branches), Conventional Commits format, PR target rules, merge methods, and commit message standards.
---

# Git Convention

## Branches

```
main ← demo / stable
 ↑
dev  ← integration
 ↑
feat/* · fix/* · chore/* · exp/*
```

| Branch | Role |
| --- | --- |
| `main` | Stable. Never push directly. |
| `dev` | Integration. |
| `feat/*` | New features. Delete after merge. |
| `fix/*` | Bug fixes. Delete after merge. |
| `chore/*` | Build / config / deps. Delete after merge. |
| `exp/*` | PoC. May keep. |

Examples: `feat/user-login`, `fix/token-expiry`, `chore/upgrade-node-20`.

## Commits

Format: `<type>(<scope>): <subject>` — scope optional.

Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`, `ci`, `exp`.

Rules:
- Imperative (`add`, not `added`).
- Subject ≤ 50 chars, no trailing period.
- One commit = one purpose.
- Body: **what** and **why**, not how.
- No `Co-Authored-By`.

Examples:
```
feat: add user login API
feat(auth): add OAuth callback handler
fix(api): handle missing response field
```

## PRs

| From | To | Merge |
| --- | --- | --- |
| `feat/*`, `fix/*`, `chore/*`, `exp/*` | `dev` | Squash |
| `dev` | `main` | Merge commit |
| `fix/*` from `main` (hotfix) | `main`, back-port to `dev` | Squash |

## Claude behavior

**New branch** — from `dev` (hotfix: from `main`):

```shellscript
git checkout dev && git pull && git checkout -b feat/xxx
```

**Tests** — include with logic changes when feasible.

**After merge** — delete branch (except `exp/*`):

```shellscript
git branch -d feat/xxx && git push origin --delete feat/xxx
```

**Hotfix → main** — back-port to `dev`:

```shellscript
git checkout dev && git pull && git merge main && git push
```