import os
import tempfile

import pytest
import toml
import yaml

from eventwatcher import config


def test_load_config(tmp_path):
    # Create a temporary config file.
    config_data = {
        "database": {"db_name": "test.db"},
        "watch_groups_config": "watch_groups.yaml"
    }
    config_file = tmp_path / "config.toml"
    with open(config_file, "w") as f:
        toml.dump(config_data, f)

    loaded_config = config.load_config(str(config_file))
    assert loaded_config["database"]["db_name"] == "test.db"
    assert loaded_config["watch_groups_config"] == "watch_groups.yaml"

def test_load_watch_groups_config(tmp_path):
    # Create a temporary watch groups YAML file.
    watch_groups_data = {
        "watch_groups": [
            {"name": "Test Group", "watch_items": ["/tmp"]}
        ]
    }
    yaml_file = tmp_path / "watch_groups.yaml"
    with open(yaml_file, "w") as f:
        yaml.dump(watch_groups_data, f)

    loaded_groups = config.load_watch_groups_config(str(yaml_file))
    assert "watch_groups" in loaded_groups
    assert loaded_groups["watch_groups"][0]["name"] == "Test Group"
