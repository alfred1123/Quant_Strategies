"""``config/db-targets.json`` is the only place that says what local and prod are.

Three things have to stay true for that to hold: the Python resolver reads it,
the shell resolver agrees field for field, and the file actually reaches the
container that needs it at startup.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from quant.shared import config as cfg

ROOT = Path(__file__).resolve().parents[2]
DB_TARGET_LIB = ROOT / "scripts" / "lib" / "db-target.sh"

_DB_ENV_VARS = (
    "DB_TARGET", "QUANTDB_HOST", "QUANTDB_PORT", "QUANTDB_NAME",
    "QUANTDB_USERNAME", "QUANTDB_PASSWORD", "QUANTDB_CONNINFO", "PROD_DB_PORT",
    "LOCAL_DB_HOST", "LOCAL_DB_PORT", "LOCAL_DB_NAME", "LOCAL_DB_USER",
    "LOCAL_DB_PASSWORD",
)


@pytest.fixture
def clean_env(monkeypatch):
    """No DB variables set, so the file's own defaults are what is under test."""
    for var in _DB_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    cfg._db_targets.cache_clear()
    yield monkeypatch
    cfg._db_targets.cache_clear()


@pytest.fixture
def spec() -> dict:
    with open(cfg.DB_TARGETS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_declares_exactly_local_and_prod(spec):
    assert set(spec["targets"]) == {cfg.LOCAL, cfg.PROD}


def test_defaults_to_prod_so_a_bare_checkout_points_somewhere_real(clean_env):
    assert cfg.db_target() == cfg.PROD


def test_local_is_loopback_5432_without_tls(clean_env):
    settings = cfg.db_settings(cfg.LOCAL)
    assert (settings["host"], settings["port"]) == ("127.0.0.1", "5432")
    assert settings["sslmode"] == "disable"


def test_prod_is_the_tunnel_port_with_tls(clean_env):
    settings = cfg.db_settings(cfg.PROD)
    assert settings["port"] == "5433"
    assert settings["sslmode"] == "require"


def test_prod_ships_no_password(spec):
    """A committed prod password is the one thing this file must never hold."""
    assert spec["targets"][cfg.PROD]["fields"]["password"]["default"] is None


def test_unknown_target_is_rejected_by_name(clean_env):
    clean_env.setenv("DB_TARGET", "qa")
    with pytest.raises(ValueError, match="local, prod"):
        cfg.db_target()


def test_db_target_is_case_and_whitespace_insensitive(clean_env):
    clean_env.setenv("DB_TARGET", "  LOCAL ")
    assert cfg.db_target() == cfg.LOCAL


def test_env_overrides_the_declared_default(clean_env):
    """How one prod entry serves both a laptop tunnel and the EC2 host."""
    clean_env.setenv("QUANTDB_HOST", "cluster.rds.amazonaws.com")
    clean_env.setenv("QUANTDB_PORT", "5432")
    settings = cfg.db_settings(cfg.PROD)
    assert (settings["host"], settings["port"]) == ("cluster.rds.amazonaws.com", "5432")


def test_prod_port_prefers_prod_db_port_over_quantdb_port(clean_env):
    clean_env.setenv("QUANTDB_PORT", "5432")
    clean_env.setenv("PROD_DB_PORT", "5433")
    assert cfg.db_settings(cfg.PROD)["port"] == "5433"


def test_empty_env_var_falls_back_to_the_default(clean_env):
    """docker-compose passes LOCAL_DB_* through as empty when .env omits them."""
    clean_env.setenv("LOCAL_DB_PORT", "")
    assert cfg.db_settings(cfg.LOCAL)["port"] == "5432"


def test_local_ignores_prod_variables(clean_env):
    """The bug this file exists to kill: .env's prod values leaking into local."""
    clean_env.setenv("QUANTDB_HOST", "cluster.rds.amazonaws.com")
    clean_env.setenv("QUANTDB_PORT", "5433")
    settings = cfg.db_settings(cfg.LOCAL)
    assert (settings["host"], settings["port"]) == ("127.0.0.1", "5432")


# ---------------------------------------------------------------------------
# The guard: prod must never resolve onto the local database
# ---------------------------------------------------------------------------

def test_prod_on_the_local_port_is_refused(clean_env):
    """A stale QUANTDB_PORT in .env would otherwise send prod to the laptop."""
    clean_env.setenv("QUANTDB_PORT", "5432")
    with pytest.raises(ValueError, match="local database"):
        cfg.db_settings(cfg.PROD)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_the_guard_covers_every_spelling_of_loopback(clean_env, host):
    clean_env.setenv("QUANTDB_HOST", host)
    clean_env.setenv("QUANTDB_PORT", "5432")
    with pytest.raises(ValueError, match="local database"):
        cfg.db_settings(cfg.PROD)


def test_the_guard_allows_aurora_on_5432(clean_env):
    """On EC2 prod really is port 5432 — the host is what distinguishes it."""
    clean_env.setenv("QUANTDB_HOST", "cluster.rds.amazonaws.com")
    clean_env.setenv("QUANTDB_PORT", "5432")
    assert cfg.db_settings(cfg.PROD)["port"] == "5432"


def test_the_guard_does_not_fire_on_the_local_target(clean_env):
    """Loopback:5432 is the whole point of local."""
    assert cfg.db_settings(cfg.LOCAL)["port"] == "5432"


# ---------------------------------------------------------------------------
# Shell twin
# ---------------------------------------------------------------------------

def _resolve_in_shell(target: str, env: dict[str, str] | None = None) -> dict[str, str]:
    """Run the shell resolver and return the DB_* values it exported."""
    script = f"""
      set -euo pipefail
      source {DB_TARGET_LIB}
      DB_TARGET={target} db_target_env
      printf 'host=%s\\nport=%s\\ndbname=%s\\nuser=%s\\nsslmode=%s\\n' \
        "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "$DB_SSLMODE"
    """
    # env= replaces the environment wholesale, which is what keeps a developer's
    # own exported QUANTDB_* out of the comparison.
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True, cwd=ROOT,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", **(env or {})},
    )
    if proc.returncode != 0:
        raise AssertionError(f"shell resolver failed: {proc.stderr}")
    return dict(
        line.split("=", 1) for line in proc.stdout.strip().splitlines() if "=" in line
    )


@pytest.mark.parametrize("target", [cfg.LOCAL, cfg.PROD])
def test_shell_and_python_resolve_a_target_identically(clean_env, target):
    """Drift between the two is how a script and the app end up on different
    databases, which is exactly what the shared file is meant to prevent."""
    shell = _resolve_in_shell(target)
    python = cfg.db_settings(target)
    for field in ("host", "port", "dbname", "user", "sslmode"):
        assert shell[field] == python[field], f"{target}.{field} differs"


def test_shell_resolver_rejects_an_unknown_target():
    with pytest.raises(AssertionError, match="local' or 'prod"):
        _resolve_in_shell("qa")


def test_shell_resolver_refuses_prod_on_the_local_port():
    with pytest.raises(AssertionError, match="local"):
        _resolve_in_shell(cfg.PROD, env={"QUANTDB_PORT": "5432"})


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------

def test_the_image_ships_the_file_it_cannot_start_without():
    """config.py reads it at startup, so a missing COPY is a production outage."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "config/db-targets.json" in dockerfile


def test_a_missing_file_names_itself(clean_env, tmp_path):
    clean_env.setattr(cfg, "DB_TARGETS_PATH", tmp_path / "absent.json")
    cfg._db_targets.cache_clear()
    with pytest.raises(RuntimeError, match="absent.json"):
        cfg.db_target()


def test_no_script_still_hardcodes_the_connection_settings():
    """Six copies of these defaults is what this file replaced; keep it at one."""
    tracked = subprocess.run(
        ["git", "ls-files", "scripts", "docker-compose.dev.yml"],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout.split()
    offenders = []
    for name in tracked:
        path = ROOT / name
        if not path.is_file() or path.name == "db-target.sh":
            continue
        text = path.read_text(errors="ignore")
        for line in text.splitlines():
            if "LetsGetRich888" in line and "App" not in line:
                offenders.append(f"{name}: {line.strip()}")
    assert not offenders, (
        "hardcoded local password outside config/db-targets.json:\n"
        + "\n".join(offenders)
    )
