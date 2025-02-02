import logging
import os

def setup_logger(name, log_dir, log_filename, level=logging.INFO, console=True):
    """
    Set up and return a logger with file and optional console handlers.

    Args:
        name (str): Name of the logger.
        log_dir (str): Directory where log file will be stored.
        log_filename (str): Log file name.
        level (int): Logging level.
        console (bool): Whether to add a console handler.

    Returns:
        logging.Logger: Configured logger.
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # File handler
    file_handler = logging.FileHandler(os.path.join(log_dir, log_filename))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger
