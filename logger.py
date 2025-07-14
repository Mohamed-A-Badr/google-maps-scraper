import logging
import os

log_file = "exception.log"
info_log_file = "info.log"

if not os.path.exists(log_file):
    with open(log_file, "w") as f:
        f.write("")

if not os.path.exists(info_log_file):
    with open(info_log_file, "w") as f:
        f.write("")

logger = logging.getLogger("logger")
logger.setLevel(logging.ERROR)

info_logger = logging.getLogger("info_logger")
info_logger.setLevel(logging.INFO)

logger.handlers.clear()

file_handler = logging.FileHandler(filename=log_file, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

info_file_handler = logging.FileHandler(filename=info_log_file, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
info_file_handler.setFormatter(formatter)

info_logger.addHandler(info_file_handler)


file_path = "country_boundary_exception.log"
if not os.path.exists(file_path):
    with open(file_path, "w") as f:
        f.write("")

country_logger = logging.getLogger("country_logger")
country_logger.setLevel(logging.ERROR)

country_logger.handlers.clear()

file_handler = logging.FileHandler(filename=file_path, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

country_logger.addHandler(file_handler)
