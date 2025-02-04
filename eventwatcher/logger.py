import logging
import os

def setup_logger(name, log_dir, log_filename, level=logging.INFO, console=True):
    """
    Set up and return a logger with file and (optionally) console handlers.

    Args:
        name (str): The logger name.
        log_dir (str): Directory where the log file will be stored.
        log_filename (str): Log file name.
        level (int): Logging level.
        console (bool): Whether to add a console handler.

    Returns:
        logging.Logger: The configured logger.
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear out any existing handlers.
    logger.handlers = []

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # File handler with the specified level.
    file_handler = logging.FileHandler(os.path.join(log_dir, log_filename))
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Optional console handler.
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
