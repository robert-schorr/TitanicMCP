# Proposal

## Why

The four documented quality gates and the container smoke test currently run only by hand. Regressions in linting, typing, tests, or the Docker image can reach `main` unnoticed, and the container deployment has no automated verification at all.

## What Changes

- Add one GitHub Actions workflow, `.github/workflows/ci.yml`, triggered by pull requests and pushes to `main`.
- Run `ruff check`, `ruff format --check`, and `ty check` in a quality job.
- Run unit tests (`tests/domain` and `tests/security`) and integration tests (`tests/integration`) as separate jobs so a failure identifies the layer.
- Run the existing `scripts/test_container.py` in a container job to build the image and verify health, a real tool call, and the non-root runtime user.
- Install dependencies from `uv.lock` with `uv sync --locked`, use read-only workflow permissions, and cancel superseded runs on the same ref.
- Stay Linux-only on `ubuntu-latest`. No Windows or macOS runners, coverage upload, image publishing, or repository secrets.

## Capabilities

### New Capabilities

- `continuous-integration`: automated verification of the quality gates, unit and integration suites, and the container image on every pull request and main-branch push.

### Modified Capabilities

None.

## Impact

- Adds `.github/workflows/ci.yml`.
- Depends on the existing `scripts/test_container.py` and `data/titanic.db` being committed; the script is currently untracked.
- No application code, dependencies, database contents, or runtime configuration change.
- Checks are advisory until branch protection requires them; no repository secrets are introduced.
