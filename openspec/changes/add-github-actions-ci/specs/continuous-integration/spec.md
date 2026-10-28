# Spec Delta

## Purpose

Define the automated verification that must pass for changes to the repository, covering static analysis, tests, and the container image.

## ADDED Requirements

### Requirement: Verification on every change

The repository SHALL run automated verification for every pull request and every push to `main`.

#### Scenario: Pull request verification

- **WHEN** a pull request is opened or updated
- **THEN** the quality, unit, integration, and container checks start

#### Scenario: Main branch verification

- **WHEN** a commit is pushed to `main`
- **THEN** the same four checks run for that commit

### Requirement: Static quality gate

The CI SHALL run Ruff linting, Ruff formatting verification, and the `ty` type check, and SHALL fail when any of them reports a problem.

#### Scenario: Lint violation

- **WHEN** a change introduces a Ruff lint violation
- **THEN** the quality check fails and reports the violation

#### Scenario: Formatting or type violation

- **WHEN** a change is not Ruff-formatted or introduces a `ty` error
- **THEN** the quality check fails

#### Scenario: Clean change

- **WHEN** all three static checks pass
- **THEN** the quality check succeeds

### Requirement: Separate unit and integration checks

The CI SHALL run the unit suite and the integration suite as separate checks, and a failure in one suite SHALL NOT prevent the other suite from running.

#### Scenario: Unit failure does not block integration

- **WHEN** a unit test fails
- **THEN** the unit check fails and the integration check still runs

#### Scenario: Integration failure is independent

- **WHEN** an integration test fails
- **THEN** the integration check fails independently of the unit result

### Requirement: Unit suite scope

The unit check SHALL run the domain and security tests without starting a live server process.

#### Scenario: Unit check contents

- **WHEN** the unit check runs
- **THEN** it executes the tests under `tests/domain` and `tests/security`

### Requirement: Integration suite scope

The integration check SHALL run the integration tests, including the HTTP entrypoint test that starts a live server and calls a tool through it.

#### Scenario: Live HTTP path

- **WHEN** the integration check runs
- **THEN** it starts the HTTP entrypoint and verifies a tool call through the live server

### Requirement: Container image verification

The container check SHALL build the production image, start it with the hardened runtime settings, wait for `/healthz`, call `list_tables`, and verify the process runs as a non-root user.

#### Scenario: Healthy image

- **WHEN** the image builds and starts successfully
- **THEN** the container check passes after the health, tool, and non-root checks succeed

#### Scenario: Image regression

- **WHEN** the image fails to build, becomes unhealthy, cannot serve `list_tables`, or runs as root
- **THEN** the container check fails

### Requirement: Locked dependencies

The CI SHALL install dependencies from the committed `uv.lock` and SHALL fail when the lockfile is out of date.

#### Scenario: Stale lockfile

- **WHEN** `pyproject.toml` and `uv.lock` disagree
- **THEN** the CI fails before running the gates

### Requirement: Least-privilege, secret-free execution

The CI SHALL run with read-only repository permissions and SHALL NOT require repository secrets.

#### Scenario: Workflow permissions

- **WHEN** the workflow runs
- **THEN** its token has read-only contents access and no repository secret is referenced

### Requirement: Linux execution

All CI jobs SHALL run on Linux runners.

#### Scenario: No platform matrix

- **WHEN** the workflow is inspected
- **THEN** every job targets a Linux runner

### Requirement: Superseded run cancellation

The CI SHALL cancel an in-progress run for the same ref when a newer run starts.

#### Scenario: New push

- **WHEN** a new commit is pushed to a ref with a running CI job
- **THEN** the older run is cancelled
