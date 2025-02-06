import os
import tempfile

import pytest
import toml
import yaml
from click.testing import CliRunner

from eventwatcher import cli


@pytest.fixture
def temp_config(tmp_path):
    config_data = {
        "database": {"db_name": "test_cli.db"},
        "watch_groups_config": str(tmp_path / "watch_groups.yaml"),
    }
    config_file = tmp_path / "config.toml"
    with open(config_file, "w") as f:
        toml.dump(config_data, f)

    watch_groups_data = {
        "watch_groups": [
            {
                "name": "CLIGroup",
                "watch_items": [str(tmp_path)],
                "sample_rate": 60,
                "max_samples": 1,
                "rules": [],
            }
        ]
    }
    watch_groups_file = tmp_path / "watch_groups.yaml"
    with open(watch_groups_file, "w") as f:
        yaml.dump(watch_groups_data, f)

    return str(config_file)


def test_show_config(temp_config):
    runner = CliRunner()
    result = runner.invoke(cli.main, ["--config", temp_config, "show-config"])
    assert result.exit_code == 0
    assert "database" in result.output


def test_init_db(temp_config, tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli.main, ["--config", temp_config, "init-db"])
    assert result.exit_code == 0
    assert "Database initialized" in result.output
