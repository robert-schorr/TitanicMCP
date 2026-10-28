# container-deployment Specification

## Purpose

Provide an optional hardened container deployment for the HTTP service, with safe loopback defaults and an explicit remote-publication path.

## Requirements

### Requirement: Non-root image

The container image SHALL run the application as a non-root user and MUST NOT contain authentication tokens, `.env` files, or other secrets.

#### Scenario: Runtime user is non-root

- **WHEN** the built image is inspected or started
- **THEN** the application process runs as a non-root user

#### Scenario: No secrets in the image

- **WHEN** the image contents and build context are inspected
- **THEN** no `MCP_AUTH_TOKEN` value or local `.env` file is present

### Requirement: Hardened runtime filesystem

The default container profile SHALL use a read-only root filesystem, a read-only database mount, a writable `tmpfs` for `/tmp`, and `no-new-privileges`.

#### Scenario: Default Compose security settings

- **WHEN** the default Compose configuration is inspected
- **THEN** the root filesystem is read-only
- **AND** `data/titanic.db` is mounted read-only
- **AND** `/tmp` is a writable tmpfs
- **AND** `no-new-privileges` is enabled

#### Scenario: Database remains read-only

- **WHEN** the container serves tool calls
- **THEN** the database mount remains read-only and the source file is unchanged

### Requirement: Container healthcheck

The container deployment SHALL define a healthcheck against `/healthz` and SHALL become healthy only after the HTTP service is accepting requests.

#### Scenario: Container becomes healthy

- **WHEN** the default container starts successfully
- **THEN** its healthcheck calls `GET /healthz`
- **AND** the container reports healthy after the endpoint returns 200

### Requirement: Loopback publication by default

The default container profile SHALL bind `0.0.0.0` inside the container but publish port 8000 only on `127.0.0.1`.

#### Scenario: Default publication

- **WHEN** the default Compose profile starts
- **THEN** the host port mapping is `127.0.0.1:8000:8000`
- **AND** the MCP service is reachable locally through the published port

### Requirement: Remote publication override

The remote container override SHALL publish on the external interface and SHALL require `MCP_PROFILE=remote`, a non-empty `MCP_AUTH_TOKEN`, and an explicit allowed-host list. Startup SHALL fail if the token is missing.

#### Scenario: Remote override configuration

- **WHEN** the remote Compose override is inspected
- **THEN** it sets `MCP_PROFILE=remote`
- **AND** it publishes port 8000 on the external interface
- **AND** it requires `MCP_AUTH_TOKEN` and an allowed-host list

#### Scenario: Remote override rejects a missing token

- **WHEN** the remote override is started without `MCP_AUTH_TOKEN`
- **THEN** the service fails before serving MCP requests

### Requirement: Build-context exclusions

The container build SHALL exclude local environments, caches, tests, and secret files through `.dockerignore`.

#### Scenario: Build context is limited

- **WHEN** the image is built
- **THEN** `.env`, virtual environments, caches, test artifacts, and VCS metadata are excluded from the build context
