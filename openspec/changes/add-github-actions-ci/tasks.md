# Tasks

## 1. Baseline and prerequisites

- [ ] 1.1 Confirm `scripts/test_container.py` and `data/titanic.db` are tracked; verify with `git ls-files scripts/test_container.py data/titanic.db`.
- [ ] 1.2 Run the four documented gates locally (`uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check`) and verify all pass.
- [ ] 1.3 Run `uv run python scripts/test_container.py` with Docker and verify it builds, becomes healthy, serves `list_tables`, and reports UID 10001.

## 2. Workflow skeleton and quality job

- [ ] 2.1 Create `.github/workflows/ci.yml` with `pull_request` and `push` to `main`, `permissions: contents: read`, concurrency cancellation, and `ubuntu-latest`; verify the YAML references no repository secret.
- [ ] 2.2 Add checkout and `astral-sh/setup-uv` steps plus `uv sync --locked` to each job; verify every job installs from the lockfile before running a gate.
- [ ] 2.3 Add the `quality` job with `ruff check .`, `ruff format --check .`, and `ty check` via `uv run --no-sync`; verify each command is present after the sync step.

## 3. Unit and integration jobs

- [ ] 3.1 Add a `test` matrix with `unit` (`tests/domain tests/security`) and `integration` (`tests/integration`) entries and `fail-fast: false`; verify both entries and their pytest paths.
- [ ] 3.2 Run the suites with `uv run --no-sync pytest`; verify each matrix entry runs only its listed paths and that the two jobs have no dependency on each other.
- [ ] 3.3 Add a job timeout to the test jobs; verify the YAML bounds both entries.

## 4. Container job

- [ ] 4.1 Add the `container` job with `DOCKER_BUILDKIT=1`, `uv sync --locked`, and `uv run --no-sync python scripts/test_container.py`; verify the job invokes the script and sets the builder env.
- [ ] 4.2 Add a job timeout to the container job; verify the YAML bounds the build and smoke test.

## 5. First-run verification

- [ ] 5.1 Push the branch and open a pull request; verify `quality`, `test (unit)`, `test (integration)`, and `container` all appear and pass.
- [ ] 5.2 Push a second commit while the first run is active; verify the older run is cancelled and the newer run completes.
- [ ] 5.3 Merge to `main`; verify the same four checks run for the main-branch push.

## Workflow follow-up

- Configure branch protection to require the four checks after the first green run.
- Sync the delta spec and archive the change after merge, implementation, and tests are complete.
