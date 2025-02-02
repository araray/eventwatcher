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

    Raises:
        FileNotFoundError: If the configuration file cannot be found.
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

    Raises:
        FileNotFoundError: If the watch groups configuration file is not found.
    """
    if not os.path.exists(watch_groups_path):
        raise FileNotFoundError(f"Watch groups configuration file not found: {watch_groups_path}")
    with open(watch_groups_path, "r") as f:
        groups_config = yaml.safe_load(f)
    return groups_config
