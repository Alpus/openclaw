---
name: openclaw-dev
description: Development workflow for contributing to OpenClaw (fork, patches, PRs). Load before any push to remote openclaw repos. Covers code quality, audit, testing, and PR preparation.
---

# OpenClaw Development Workflow

Rules for developing, testing, and pushing code to OpenClaw repositories. **Load this skill before every remote push.**

## 🔴 Core Principles

1. **This is a public-facing codebase.** Treat every commit as eventually public
2. **Nothing personal.** No names, addresses, credentials, personal preferences, workspace paths, or user-specific config
3. **Clean git history.** Every commit should be meaningful, squashed, well-described
4. **Tests first.** No push without passing tests. No fix without test coverage
5. **Audit before push.** Every push goes through the full checklist below

## 📁 Repository Layout

- **Форк = наш.** `~/openclaw/` — это наш форк. Все файлы (включая skills/) можно менять свободно. Не путать с upstream — upstream мы не меняем напрямую, а делаем PR. Но в форке мы дома.
- **Upstream:** `openclaw/openclaw` (official repo)
- **Fork:** your GitHub fork (for PRs)
- **Local:** your git clone (working copy)

Store your specific paths, fork URL, and remote names in workspace (e.g., `MEMORY.md` or `TOOLS.md`).

## 🔄 Development Cycle

### 1. Branch

```bash
cd ~/openclaw
git checkout -b fix/descriptive-name
```

- Branch naming: `fix/`, `feat/`, `refactor/`, `docs/`
- One logical change per branch

### 2. Code

- Minimal diffs — change only what's needed
- Follow existing code style
- No commented-out code, no debug logs, no TODOs without issue refs

### 3. Test

```bash
pnpm vitest run src/path/to/your.test.ts        # your new test (ALWAYS)
pnpm vitest run src/path/to/related.test.ts      # related/nearby tests
```

- **Write tests BEFORE fixing** (red → green workflow)
- New code must have test coverage
- Edge cases matter — test boundaries, error paths, empty inputs
- **⚠️ NEVER run full `pnpm test` / `pnpm vitest run` without a filter** — the full suite is 500+ tests, takes forever, and can OOM the machine. Run only: (1) your new test, (2) tests for files you changed, (3) a few related tests nearby. That's enough for a PR — CI will run the full suite.

### 4. Pre-push Audit (MANDATORY)

Run this checklist before every `git push`:

#### a) No personal data

```bash
# Search for personal info in staged changes
git diff --cached | grep -iE '(@gmail|1password|openclaw\.json|/Users/|/home/)'
```

Must return nothing.

#### b) No credentials

```bash
git diff --cached | grep -iE '(password|token|api.key|secret|Bearer|sk-|ghp_|github_pat|op_)'
```

Must return nothing (or only test fixtures with obviously fake values).

#### c) No workspace/config paths

```bash
git diff --cached | grep -iE '(\.openclaw/|/Users/|home/|workspace/)'
```

Should return nothing in production code (OK in comments explaining architecture).

#### d) Tests pass

```bash
pnpm test
```

All green.

#### e) Review full diff

```bash
git log --oneline origin/main..HEAD   # commits to push
git diff origin/main..HEAD            # full diff
```

Read every line. Ask: "Would I be comfortable if this were on the front page of Hacker News?"

#### f) Commit quality

- Squash WIP commits: `git rebase -i origin/main`
- Clear commit messages: `type(scope): description`
- Example: `fix(telegram): strip message_thread_id for DM replies`

### 5. Push

```bash
git push origin fix/descriptive-name
```

### 6. PR

```bash
gh pr create --repo openclaw/openclaw --title "fix(telegram): ..." --body "..."
```

- PR description: what, why, how, test coverage
- Reference related issues
- Keep scope small — easier to review

## 🔧 Local Deploy (Testing before push)

```bash
cd ~/openclaw
pnpm build
launchctl kickstart -k gui/501/ai.openclaw.gateway
```

- Test the actual running gateway, not just unit tests
- Verify the fix works end-to-end
- **После ребейза/build: ВСЕГДА проверить что gateway стартует** (`openclaw gateway start` или `openclaw doctor`). Не игнорировать ошибки build даже если "только dts". Инцидент 2026-02-14: проигнорировала TS ошибку `https-proxy-agent` → crash при старте
- **НИКОГДА `git checkout/restore` отдельных файлов при rebase** — откатывает к старой версии, теряет upstream код. Инцидент 2026-02-16: checkout send.ts удалил sendPollTelegram → crash ×2. Вместо: разрешать конфликты вручную в каждом файле
- **После ANY git операции → `pnpm build`** — dist/ не обновляется автоматически. Gateway запускает dist/, не src/
- Check logs: `/tmp/openclaw/openclaw-*.log`

## 🔀 Fork Maintenance

We maintain forks with local patches on top of upstream. Track all forks in a workspace file (e.g., `infra/forks.md`) with: local path, fork remote, upstream remote, branch, strategy, and list of patches.

### Adding a new fork

When you start tracking a new fork:

1. Add it to `infra/forks.md` with all fields
2. Set up remotes: `origin` = our fork, `upstream` = original repo
3. Note all local patches in the entry

### Update procedure (automated, part of Saturday digest)

For each fork in `infra/forks.md`:

```bash
cd <local_path>
git fetch <upstream_remote>
# Check how far behind
git log --oneline HEAD..<upstream_remote>/<branch> | wc -l
```

**If 0 commits behind** → skip, report "up to date".

**If commits behind, try rebase:**

```bash
git rebase <upstream_remote>/<branch>
```

**If rebase succeeds (no conflicts):**

1. `npm run build` (or equivalent) — verify build passes
2. Run tests if available
3. `git push <fork_remote> <branch> --force-with-lease`
4. If submodule — update pointer in parent repo and push parent
5. Report: "✅ <name>: rebased N commits, build OK"

**If rebase has conflicts:**

1. `git rebase --abort`
2. Report: "⚠️ <name>: N commits behind, conflicts in [files]. Needs manual merge."
3. Create a task for manual resolution

### Principles

- **Always rebase, never merge** — clean linear history
- **`--force-with-lease`** not `--force` — prevents overwriting others' work
- **Build + test after rebase** — don't push broken code
- **Report everything** — human decides on conflicts
- **Don't auto-deploy** after openclaw rebase — just report, user decides when to restart gateway

## ⚠️ Common Mistakes

- Pushing with hardcoded user paths (`/Users/<username>/...`)
- Leaving debug `console.log` statements
- Forgetting to run tests after "small" changes
- Not squashing WIP commits before push
- Including unrelated changes in the same commit

## 🔧 Operational Lessons

- **config.ts + openclaw.plugin.json** — update BOTH in sync when changing schema
- **Restart**: SIGUSR1 or config.patch. NEVER kill. `kickstart -k` for TS changes
- **SIGUSR1 caches TS** — full restart needed to pick up TS changes
- **Strict validation**: unknown keys = gateway won't start
- **Before config changes — search docs.** Invalid config = hours offline
- **Backup config**: `cp openclaw.json openclaw.json.bak` before any change
- Plugin logs: `/tmp/openclaw/openclaw-YYYY-MM-DD.log` (not gateway.log)
- **LaunchAgent caches arguments** — bootout+bootstrap when changing plist
