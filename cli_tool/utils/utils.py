import os
import logging
from datetime import datetime
from pathlib import Path

def log_message(message, level='info', log_file=None):
    logger = logging.getLogger('utils_logger')
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    getattr(logger, level.lower(), logger.info)(message)

def create_directories(path):
    Path(path).mkdir(parents=True, exist_ok=True)

def read_file(file_path, mode='r'):
    with open(file_path, mode) as f:
        return f.read()

def write_file(file_path, data, mode='w'):
    with open(file_path, mode) as f:
        f.write(data)

def get_timestamp(fmt='%Y-%m-%d_%H-%M-%S'):
    return datetime.now().strftime(fmt)

def list_files(directory, extension=None):
    files = []
    for entry in os.listdir(directory):
        if os.path.isfile(os.path.join(directory, entry)):
            if extension is None or entry.endswith(extension):
                files.append(entry)
    return files

def safe_remove(file_path):
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass

def is_valid_file(file_path):
    return os.path.isfile(file_path)
