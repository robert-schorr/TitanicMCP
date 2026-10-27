from __future__ import annotations

from pathlib import Path

import pytest

from titanic_mcp.database import Database
from titanic_mcp.server import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_HOST,
    DEFAULT_PORT,
    ConfigurationError,
    ServerConfig,
    default_config,
    http_app,
    load_config,
    validate_config,
)


def test_default_config_is_safe_and_local() -> None:
    config = load_config({})

    assert config.database_path == DEFAULT_DATABASE_PATH
    assert config.host == DEFAULT_HOST
    assert config.port == DEFAULT_PORT
    assert config.profile == "local"
    assert config.auth_token is None
    assert config.allowed_hosts == ()
    assert config.allowed_origins == ()
    assert config.log_level == "INFO"
    assert config.log_format == "json"
    assert config.stateless_http is True
    assert config.host_origin_protection == "auto"


def test_default_config_does_not_read_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_PROFILE", "remote")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "process-token")

    config = default_config()

    assert config.profile == "local"
    assert config.auth_token is None


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "LOCALHOST", "::1", "[::1]", "127.0.0.2"],
)
def test_local_profile_accepts_loopback_bind_hosts(host: str) -> None:
    config = load_config({"MCP_PROFILE": "local", "TITANIC_MCP_HOST": host})

    assert config.profile == "local"
    assert config.stateless_http is True


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "192.168.1.10", "example.com", "::", "[2001:db8::1]"],
)
def test_local_profile_rejects_non_loopback_bind_hosts(host: str) -> None:
    with pytest.raises(ConfigurationError, match="TITANIC_MCP_HOST") as exc_info:
        load_config({"MCP_PROFILE": "local", "TITANIC_MCP_HOST": host})

    assert host in str(exc_info.value)


def test_container_profile_defaults_to_all_interfaces() -> None:
    config = load_config(
        {
            "MCP_PROFILE": "container",
            "MCP_ALLOWED_HOSTS": "localhost:8000",
        }
    )

    assert config.host == "0.0.0.0"
    assert config.stateless_http is False
    assert config.host_origin_protection is True


def test_container_profile_starts_without_a_token() -> None:
    config = load_config(
        {
            "MCP_PROFILE": "container",
            "TITANIC_MCP_HOST": "0.0.0.0",
            "MCP_ALLOWED_HOSTS": "localhost:8000,127.0.0.1:8000",
        }
    )

    assert config.auth_token is None
    assert config.allowed_hosts == ("localhost:8000", "127.0.0.1:8000")


def test_container_profile_accepts_an_optional_token() -> None:
    config = load_config(
        {
            "MCP_PROFILE": "container",
            "MCP_ALLOWED_HOSTS": "localhost:8000",
            "MCP_AUTH_TOKEN": "container-token",
        }
    )

    assert config.auth_token == "container-token"


@pytest.mark.parametrize("allowed_hosts", [None, "", "   ", " , , "])
def test_container_profile_requires_allowed_hosts(
    allowed_hosts: str | None,
) -> None:
    environ = {"MCP_PROFILE": "container"}
    if allowed_hosts is not None:
        environ["MCP_ALLOWED_HOSTS"] = allowed_hosts

    with pytest.raises(ConfigurationError, match="MCP_ALLOWED_HOSTS"):
        load_config(environ)


def test_remote_profile_defaults_to_all_interfaces() -> None:
    config = load_config(
        {
            "MCP_PROFILE": "remote",
            "MCP_AUTH_TOKEN": "remote-token",
            "MCP_ALLOWED_HOSTS": "mcp.example.com",
        }
    )

    assert config.host == "0.0.0.0"
    assert config.stateless_http is False
    assert config.host_origin_protection is True


def test_remote_profile_starts_with_required_settings() -> None:
    config = load_config(
        {
            "MCP_PROFILE": "remote",
            "TITANIC_MCP_HOST": "0.0.0.0",
            "MCP_AUTH_TOKEN": "remote-token",
            "MCP_ALLOWED_HOSTS": "mcp.example.com",
            "MCP_ALLOWED_ORIGINS": "https://mcp.example.com",
        }
    )

    assert config.auth_token == "remote-token"
    assert config.allowed_hosts == ("mcp.example.com",)
    assert config.allowed_origins == ("https://mcp.example.com",)


@pytest.mark.parametrize("token", [None, "", "   "])
def test_remote_profile_requires_a_non_empty_token(token: str | None) -> None:
    environ = {
        "MCP_PROFILE": "remote",
        "MCP_ALLOWED_HOSTS": "mcp.example.com",
    }
    if token is not None:
        environ["MCP_AUTH_TOKEN"] = token

    with pytest.raises(ConfigurationError, match="MCP_AUTH_TOKEN"):
        load_config(environ)


@pytest.mark.parametrize("allowed_hosts", [None, "", "   ", " , , "])
def test_remote_profile_requires_allowed_hosts(
    allowed_hosts: str | None,
) -> None:
    environ = {
        "MCP_PROFILE": "remote",
        "MCP_AUTH_TOKEN": "remote-token",
    }
    if allowed_hosts is not None:
        environ["MCP_ALLOWED_HOSTS"] = allowed_hosts

    with pytest.raises(ConfigurationError, match="MCP_ALLOWED_HOSTS"):
        load_config(environ)


def test_remote_profile_reports_every_missing_setting() -> None:
    with pytest.raises(ConfigurationError) as exc_info:
        load_config({"MCP_PROFILE": "remote"})

    message = str(exc_info.value)
    assert "MCP_AUTH_TOKEN" in message
    assert "MCP_ALLOWED_HOSTS" in message


@pytest.mark.parametrize("profile", ["staging", "remote-local", "containers"])
def test_unknown_profile_is_rejected(profile: str) -> None:
    with pytest.raises(ConfigurationError, match="MCP_PROFILE"):
        load_config({"MCP_PROFILE": profile})


def test_profile_names_are_case_insensitive() -> None:
    assert load_config({"MCP_PROFILE": "LOCAL"}).profile == "local"
    assert load_config(
        {"MCP_PROFILE": "Container", "MCP_ALLOWED_HOSTS": "h"}
    ).profile == ("container")
    assert (
        load_config(
            {
                "MCP_PROFILE": "Remote",
                "MCP_AUTH_TOKEN": "token",
                "MCP_ALLOWED_HOSTS": "h",
            }
        ).profile
        == "remote"
    )


@pytest.mark.parametrize("profile", [None, "", "   "])
def test_blank_profile_uses_the_local_default(profile: str | None) -> None:
    environ = {"MCP_PROFILE": profile} if profile is not None else {}

    assert load_config(environ).profile == "local"


def test_all_environment_overrides_are_applied() -> None:
    config = load_config(
        {
            "TITANIC_MCP_DB_PATH": "custom/titanic.db",
            "TITANIC_MCP_HOST": "0.0.0.0",
            "TITANIC_MCP_PORT": "9001",
            "MCP_PROFILE": "remote",
            "MCP_AUTH_TOKEN": "  secret-token  ",
            "MCP_ALLOWED_HOSTS": " mcp.example.com , ,localhost:8000, ",
            "MCP_ALLOWED_ORIGINS": " https://app.example.com ,, https://mcp.example.com ",
            "TITANIC_MCP_LOG_LEVEL": "debug",
            "TITANIC_MCP_LOG_FORMAT": "TEXT",
        }
    )

    assert config.database_path == Path("custom/titanic.db")
    assert config.host == "0.0.0.0"
    assert config.port == 9001
    assert config.profile == "remote"
    assert config.auth_token == "secret-token"
    assert config.allowed_hosts == ("mcp.example.com", "localhost:8000")
    assert config.allowed_origins == (
        "https://app.example.com",
        "https://mcp.example.com",
    )
    assert config.log_level == "DEBUG"
    assert config.log_format == "text"


def test_comma_separated_allowlists_discard_empty_entries() -> None:
    config = load_config(
        {
            "MCP_PROFILE": "container",
            "MCP_ALLOWED_HOSTS": "first,,second, ,third",
            "MCP_ALLOWED_ORIGINS": ",,https://one.example,,https://two.example,,",
        }
    )

    assert config.allowed_hosts == ("first", "second", "third")
    assert config.allowed_origins == (
        "https://one.example",
        "https://two.example",
    )


@pytest.mark.parametrize("port", ["not-a-port", "1.5", "eight thousand"])
def test_invalid_port_text_is_rejected(port: str) -> None:
    with pytest.raises(ConfigurationError, match="TITANIC_MCP_PORT"):
        load_config({"TITANIC_MCP_PORT": port})


@pytest.mark.parametrize("port", [None, "", "   "])
def test_blank_port_uses_the_default(port: str | None) -> None:
    environ = {"TITANIC_MCP_PORT": port} if port is not None else {}

    assert load_config(environ).port == DEFAULT_PORT


@pytest.mark.parametrize("port", ["0", "-1", "65536", "99999"])
def test_out_of_range_port_is_rejected(port: str) -> None:
    with pytest.raises(ConfigurationError, match="TITANIC_MCP_PORT"):
        load_config({"TITANIC_MCP_PORT": port})


@pytest.mark.parametrize("log_format", ["yaml", "JSONL", "plain"])
def test_invalid_log_format_is_rejected(log_format: str) -> None:
    with pytest.raises(ConfigurationError, match="TITANIC_MCP_LOG_FORMAT"):
        load_config({"TITANIC_MCP_LOG_FORMAT": log_format})


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="TITANIC_MCP_LOG_LEVEL"):
        load_config({"TITANIC_MCP_LOG_LEVEL": "verbose"})


def test_token_is_redacted_from_configuration_repr() -> None:
    config = load_config(
        {
            "MCP_PROFILE": "remote",
            "MCP_AUTH_TOKEN": "super-secret-token",
            "MCP_ALLOWED_HOSTS": "mcp.example.com",
        }
    )

    assert "super-secret-token" not in repr(config)
    assert "super-secret-token" not in str(config)


def test_validate_config_accepts_a_directly_constructed_valid_config() -> None:
    config = ServerConfig(
        profile="container",
        host="0.0.0.0",
        allowed_hosts=("localhost:8000",),
    )

    assert validate_config(config) is config


@pytest.mark.parametrize(
    "config",
    [
        ServerConfig(profile="local", host="0.0.0.0"),
        ServerConfig(profile="container", host="0.0.0.0"),
        ServerConfig(profile="remote", host="0.0.0.0"),
        ServerConfig(
            profile="remote",
            host="0.0.0.0",
            auth_token="token",
        ),
    ],
)
def test_app_creation_rejects_invalid_configurations(
    config: ServerConfig,
    database: Database,
) -> None:
    with pytest.raises(ConfigurationError):
        http_app(database, config)
