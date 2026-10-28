# Design

## Context

The repository has no `.github/` directory. Its four documented gates (`ruff check`, `ruff format --check`, `ty check`, and `pytest`) pass locally, and the suite currently contains 291 tests: 189 under `tests/domain` and `tests/security`, and 102 under `tests/integration`. Only `tests/integration/test_http_entrypoint.py` starts a real server process.

`scripts/test_container.py` already builds the production image, starts it with the Compose security settings, waits for `/healthz`, calls `list_tables` through the published port, and verifies the runtime UID is 10001. It is currently untracked. See `proposal.md` for why this change is needed.

## Goals / Non-Goals

**Goals:**

- One workflow with independent quality, unit, integration, and container checks.
- Reuse the commands and container script the project already documents.
- Fail on a stale lockfile, use read-only permissions, require no repository secrets.
- Keep the first version small enough to review and reason about.

**Non-Goals:**

- Windows or macOS runners, a Python version matrix, coverage upload, or image publishing.
- Compose YAML validation, Docker layer caching, dependency or image vulnerability scanning.
- Reorganizing tests or introducing pytest markers.
- Configuring branch protection from code.

## Decisions

### One workflow, four jobs

Use a single `.github/workflows/ci.yml` with a `quality` job, a `test` matrix containing `unit` and `integration`, and a `container` job. The jobs run in parallel with no `needs` edges, and the test matrix uses `fail-fast: false`.

This gives each concern its own required check name and keeps a unit failure from hiding an integration failure. A single linear job would duplicate less setup but produce one coarse signal. Separate workflow files would add files without adding value at this size.

### Directory-based test split

The unit check runs `pytest tests/domain tests/security`; the integration check runs `pytest tests/integration`. The security tests are in-process and do not start a live server, so they belong with the fast suite. This requires no test edits or marker configuration.

The alternative is a `unit`/`integration` marker split, which labels each test more precisely but touches the test suite and adds marker bookkeeping for no behavioral gain here.

### Reuse `scripts/test_container.py`

The container job runs `uv run --no-sync python scripts/test_container.py` after the environment is synced. The script already verifies build, hardened runtime settings, health, a real tool call, and non-root UID.

The alternative is a Docker-aware pytest test that skips when Docker is unavailable. That improves reporting and keeps one test command, but slows local runs, adds skip logic, and duplicates what the script already proves.

### Locked install, then no-sync runs

Each job runs `uv sync --locked` once, then executes gates with `uv run --no-sync`. `--locked` fails when `pyproject.toml` and `uv.lock` disagree; `--no-sync` avoids repeating dependency resolution for every command.

Using plain `uv run` per command would work but hides lockfile drift behind an implicit sync. `--frozen` would use the lock without checking whether it is current.

### Linux only

Every job uses `ubuntu-latest`. The deployed artifact is a Linux container, and the only Windows-specific code is the process-stop fallback in the entrypoint test. A Windows matrix would add wall-clock time and process-management flakiness without increasing confidence in the shipped image.

If developer-platform coverage becomes a goal, the test matrix can add `windows-latest` later; `quality` and `container` stay on Linux because Windows runners cannot run Linux containers.

### Caching and action versions

Use `astral-sh/setup-uv` with its default dependency cache. Do not add a Docker layer cache yet: the existing script owns the build, and wiring `docker/build-push-action` with GitHub Actions cache would require splitting build from smoke test or changing the script. Measure the cold build first.

Use `actions/checkout@v7` and `astral-sh/setup-uv@v10` at their major tags. Pinning both by commit SHA is a later supply-chain hardening step, not a requirement for the first version.

### Execution safety

Set workflow permissions to `contents: read`, reference no secrets, and use a concurrency group keyed by workflow and ref with `cancel-in-progress: true`. Set `DOCKER_BUILDKIT=1` for the container job because the Dockerfile uses `RUN --mount=type=cache`, and add a job timeout so a hung build or test cannot occupy a runner indefinitely.

## Risks / Trade-offs

- **The Linux suites have not been run in this repo.** The integration tests are exercised on Windows locally, and the POSIX process-stop path is untested here. Mitigation: the first CI run validates it; run the integration suite in a Linux container locally if the first run fails.
- **The container script is untracked.** The container job fails if `scripts/test_container.py` is not committed. Mitigation: commit the script and `data/titanic.db` with the workflow.
- **The Docker script has not been run end-to-end since the last Dockerfile change.** Mitigation: run it locally with Docker before merging, or treat the first CI run as the validation.
- **Cold Docker builds dominate CI time.** Mitigation: measure the first runs; add GitHub Actions layer caching only if the job becomes the bottleneck.
- **Base image pulls can fail transiently.** Mitigation: rerun the container job; pin or mirror base images later if it becomes recurrent.
- **Checks are advisory until branch protection is configured.** Mitigation: require all four checks after the first green run.
- **`ubuntu-latest` can move.** Mitigation: pin `ubuntu-24.04` if runner drift ever causes a surprise.

## Migration Plan

1. Commit `scripts/test_container.py`, `data/titanic.db`, and the workflow.
2. Open a pull request and confirm all four checks pass.
3. Configure branch protection to require `quality`, `test (unit)`, `test (integration)`, and `container`.
4. Rollback is deleting the workflow; it has no runtime effect.
