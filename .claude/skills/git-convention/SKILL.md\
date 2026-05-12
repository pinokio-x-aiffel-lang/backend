---
name: git-convention
description: Use this skill whenever the user asks to create commits, write commit messages, create branches, open pull requests, merge branches, or push to remote. Enforces this project's branch strategy (main/develop with feat/fix/chore/exp working branches), Conventional Commits format, PR target rules, merge methods, and commit message standards.
---

# Git Convention

## Branch Structure

```
main      ← External demo / stable (auto-deploys to staging)
 ↑
develop   ← Integration line (auto-deploys to dev)
 ↑
feat/*, fix/*, chore/*, exp/*
```

| Branch | Role | Notes |
| --- | --- | --- |
| `main` | Demo-ready stable version | Never push directly |
| `develop` | Where all work integrates | |
| `feat/*` | New features | Delete after merge |
| `fix/*` | Bug fixes | Delete after merge |
| `chore/*` | Build, config, deps, maintenance | Delete after merge |
| `exp/*` | Experimental / PoC attempts | May be kept |

Branch name examples:

```
feat/user-login
fix/token-expiry
chore/upgrade-node-20
exp/vector-search
```

## Commit Message Convention

Format:

```
<type>(<scope>): <subject>
```

- `scope` is optional. Use it when the change is clearly scoped (e.g., `auth`, `api`, `db`).
- Examples:
  ```
  feat: add user login API
  feat(auth): add OAuth callback handler
  fix(api): handle missing response field
  chore: bump pnpm to 10.x
  ```

Allowed types:

| Type | Use for |
| --- | --- |
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring (no behavior change) |
| `perf` | Performance improvement |
| `docs` | Documentation only |
| `test` | Test code |
| `chore` | Build, config, dependencies, maintenance |
| `ci` | CI/CD pipeline changes |
| `exp` | Experimental / PoC attempt |

Writing rules:

- Use the imperative mood (`add`, not `added`)
- Subject line ≤ 50 characters
- No trailing period in the subject
- One commit = one purpose
- The body (when present) explains **what** changed and **why**, not how
- Do **not** include a `Co-Authored-By` line in commits

## PR Rules

| PR | From | To | Merge method |
| --- | --- | --- | --- |
| Day-to-day | `feat/*`, `fix/*`, `chore/*`, `exp/*` | `develop` | Squash |
| Demo release | `develop` | `main` | Merge commit |
| Hotfix | `fix/*` (branched from `main`) | `main`, then back-port to `develop` | Squash |

## Claude's Required Behavior

**When creating a branch** — branch from `develop` (or `main` for hotfix only):

```bash
git checkout develop && git pull && git checkout -b feat/xxx
```

**Before `git push`**:

- On `main` → **STOP and warn the user**. Direct push is forbidden.
- On `develop` → confirm with the user once.
- On a working branch → proceed.

**When writing a commit** — follow the Commit Message Convention above. Never add `Co-Authored-By`.

**Including tests** — when adding or changing application logic, include unit tests in the same commit when feasible.

**After a merge** — delete the working branch, except `exp/*`:

```bash
git branch -d feat/xxx && git push origin --delete feat/xxx
```

**After a hotfix is merged to `main`** — back-port to `develop`:

```bash
git checkout develop && git pull && git merge main && git push
```

## Never

- Push directly to `main`
- Merge a working branch into `main` (must go through `develop`)
- Use Squash for `develop` → `main` (must be a Merge commit)
- Skip Conventional Commits format
- Include `Co-Authored-By` in commit messages
