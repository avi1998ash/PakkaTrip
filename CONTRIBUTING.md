# Branching & release workflow

```
main ──────────●──────────────●──────●──▶   released code only, every merge tagged (v0.1.0, v0.2.0 …)
               ↑ merge + tag  ↑ merge ↑ merge
release/0.2 ───┘              hotfix/0.2.1 ─┘     cut from main
   ↑ cut       │ back-merge         │ back-merge
develop ──●────●────────────────────●────────▶   where everyone's work comes together
          ↑ PR + review + CI pass
feature/<name>/<ticket> ──●──●                   cut from develop
```

| Branch | Cut from | Merges into | Notes |
|---|---|---|---|
| `main` | — | — | Only released code. Never commit directly. Every merge gets a tag `vX.Y.Z`. |
| `develop` | `main` | — | Integration branch. Changes arrive only by pull request. |
| `feature/<name>/<ticket>` | `develop` | `develop` (PR) | e.g. `feature/rahul/JIRA-123`. PR needs a review and green CI. |
| `release/X.Y` | `develop` | `main` (+ tag `vX.Y.0`), then back-merge to `develop` | Only bug fixes and version bumps on this branch. |
| `hotfix/X.Y.Z` | `main` | `main` (+ tag `vX.Y.Z`), then back-merge to `develop` | Urgent production fixes only. |

## Day-to-day

```bash
# start a feature
git checkout develop && git pull
git checkout -b feature/<your-name>/<ticket>
# ...commit work...
git push -u origin feature/<your-name>/<ticket>
# open a PR into develop; merge after review + CI pass
```

## Cutting a release

```bash
git checkout develop && git pull
git checkout -b release/0.2
git push -u origin release/0.2
# QA on the release branch; fix bugs here only
# PR release/0.2 -> main, merge, then tag:
git checkout main && git pull
git tag -a v0.2.0 -m "Release 0.2.0" && git push origin v0.2.0
# back-merge so develop gets the release fixes
git checkout develop && git merge --no-ff main && git push
```

## Hotfix

```bash
git checkout main && git pull
git checkout -b hotfix/0.2.1
# fix, commit, push, PR into main, merge, then:
git checkout main && git pull
git tag -a v0.2.1 -m "Hotfix 0.2.1" && git push origin v0.2.1
git checkout develop && git merge --no-ff main && git push
```

## CI

`.github/workflows/ci.yml` runs on every PR and push to `develop`, `main`, `release/**` and `hotfix/**`:
backend (`manage.py check`, missing-migration check, `manage.py test api` against PostgreSQL 18) and
frontend (`npm ci`, `npm run build`).

## Never commit

`backend/.env`, `database/setup_db.sql`, `backend/media/`, `.venv/`, `node_modules/`, `dist/`.
Use `backend/.env.example` and `database/setup_db.example.sql` as templates.
