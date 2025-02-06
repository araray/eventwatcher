import os

import toml
import yaml

DEFAULT_CONFIG_PATH = "./config.toml"
ENV_CONFIG_DIR_VAR = "EVENTWATCHER_CONFIG_DIR"


def load_config(cli_config_path=None):
    """
    Load configuration from a TOML file.

    Precedence:
      1. cli_config_path if provided.
      2. Environment variable EVENTWATCHER_CONFIG_DIR (looking for config.toml).
      3. Default to ./config.toml.

    Returns:
        dict: The configuration settings.
    """
    config_path = None
    if cli_config_path:
        config_path = cli_config_path
    elif os.environ.get(ENV_CONFIG_DIR_VAR):
        config_path = os.path.join(os.environ[ENV_CONFIG_DIR_VAR], "config.toml")
    else:
        config_path = DEFAULT_CONFIG_PATH

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r") as f:
        config_data = toml.load(f)

    return config_data


def load_watch_groups_config(watch_groups_path):
    """
    Load watch groups configuration from a YAML file.

    Args:
        watch_groups_path (str): Path to the YAML configuration file.

    Returns:
        dict: Watch groups configuration.
    """
    if not os.path.exists(watch_groups_path):
        raise FileNotFoundError(
            f"Watch groups configuration file not found: {watch_groups_path}"
        )
    with open(watch_groups_path, "r") as f:
        groups_config = yaml.safe_load(f)
    return groups_config


def load_watch_groups_configs(path):
    """
    Load watch groups configuration from a YAML file or a directory containing YAML files.
    If a directory is provided, all .yaml/.yml files are loaded and aggregated.

    Args:
        path (str): Path to a YAML file or directory.

    Returns:
        dict: Aggregated watch groups configuration with key 'watch_groups'.
    """
    if os.path.isdir(path):
        aggregated = {"watch_groups": []}
        for filename in os.listdir(path):
            if filename.endswith((".yaml", ".yml")):
                file_path = os.path.join(path, filename)
                with open(file_path, "r") as f:
                    data = yaml.safe_load(f)
                    if data and "watch_groups" in data:
                        aggregated["watch_groups"].extend(data["watch_groups"])
        return aggregated
    else:
        return load_watch_groups_config(path)
