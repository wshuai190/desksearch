"""Tests for the CLI entry point (__main__.py)."""
import os
import pytest
from click.testing import CliRunner

from desksearch.__main__ import cli


@pytest.fixture
def runner(tmp_path):
    """Click test runner with isolated data dir."""
    env = {
        "DESKSEARCH_DATA_DIR": str(tmp_path / "data"),
        "TOKENIZERS_PARALLELISM": "false",
        "KMP_DUPLICATE_LIB_OK": "TRUE",
    }
    return CliRunner(env=env)


class TestHelpPages:
    """Regression: --help must show usage text, not start the server (GH-fix)."""

    @pytest.mark.parametrize("cmd", [
        [],
        ["serve"],
        ["index"],
        ["search"],
        ["config"],
        ["config", "show"],
        ["config", "set"],
        ["config", "get"],
        ["config", "list"],
        ["benchmark"],
        ["doctor"],
        ["daemon"],
        ["daemon", "start"],
        ["daemon", "stop"],
        ["daemon", "status"],
        ["folders"],
        ["folders", "list"],
        ["folders", "add"],
        ["folders", "remove"],
        ["setup"],
        ["stats"],
        ["status"],
    ])
    def test_help_shows_usage(self, runner, cmd):
        result = runner.invoke(cli, [*cmd, "--help"])
        assert result.exit_code == 0, f"cmd={cmd!r} failed: {result.output}"
        assert "Usage:" in result.output, f"cmd={cmd!r} missing Usage: {result.output}"


class TestVersion:
    def test_version_flag(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()


class TestConfigCommands:
    def test_config_show(self, runner):
        result = runner.invoke(cli, ["config", "show", "--json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "embedding_model" in data

    def test_config_list_is_alias(self, runner):
        result = runner.invoke(cli, ["config", "list", "--json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "embedding_model" in data

    def test_config_get(self, runner):
        result = runner.invoke(cli, ["config", "get", "port"])
        assert result.exit_code == 0
        assert "port" in result.output

    def test_config_get_unknown_key(self, runner):
        result = runner.invoke(cli, ["config", "get", "nonexistent_key"])
        assert result.exit_code != 0

    def test_config_set_and_get(self, runner):
        result = runner.invoke(cli, ["config", "set", "port", "4000"])
        assert result.exit_code == 0
        assert "4000" in result.output

        result = runner.invoke(cli, ["config", "get", "port", "--json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["value"] == 4000

    def test_config_set_unknown_key(self, runner):
        result = runner.invoke(cli, ["config", "set", "bad_key", "value"])
        assert result.exit_code != 0


class TestDoctorCommand:
    def test_doctor_json(self, runner):
        """Doctor should run without crashing (some checks may fail in test env)."""
        result = runner.invoke(cli, ["doctor", "--json"])
        # May exit 0 or 1 depending on available packages, but should not crash
        import json
        data = json.loads(result.output)
        assert "healthy" in data
        assert "checks" in data


class TestStatusCommand:
    def test_status_json(self, runner):
        result = runner.invoke(cli, ["status", "--json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "documents" in data
        assert "chunks" in data


class TestFoldersCommands:
    def test_folders_list_empty(self, runner):
        result = runner.invoke(cli, ["folders", "list"])
        # Fresh config has default folders (may or may not exist)
        assert result.exit_code == 0

    def test_folders_add_and_list(self, runner, tmp_path):
        target = tmp_path / "testdir"
        target.mkdir()
        result = runner.invoke(cli, ["folders", "add", str(target)])
        assert result.exit_code == 0
        assert "Added" in result.output or "✓" in result.output
