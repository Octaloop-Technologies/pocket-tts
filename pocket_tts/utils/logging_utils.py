import logging
from contextlib import contextmanager


class PackageFilter(logging.Filter):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__()

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith(self.name)


@contextmanager
def enable_logging(
    library_name: str,
    level: int,
    filter_by_name: bool = True,
):
    """
    Enable logging for the given library.
    If filter_by_name is True (default), only logs from modules starting with
    library_name are shown. Set to False to see all logs (useful for debugging).
    """
    logger = logging.getLogger(library_name)
    parent_logger = logging.getLogger(library_name.split(".")[0])  # root of package

    old_level = logger.level
    old_parent_level = parent_logger.level
    old_handlers = parent_logger.handlers.copy()

    parent_logger.setLevel(level)
    parent_logger.handlers.clear()

    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    handler.setFormatter(formatter)

    if filter_by_name:
        handler.addFilter(PackageFilter(library_name))

    parent_logger.addHandler(handler)
    parent_logger.propagate = False

    try:
        yield logger
    finally:
        logger.setLevel(old_level)
        parent_logger.setLevel(old_parent_level)
        parent_logger.handlers.clear()
        for h in old_handlers:
            parent_logger.addHandler(h)
