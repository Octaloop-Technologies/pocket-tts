import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get() or "no-id"
        return True


def setup_logging():
    logger = logging.getLogger("pocket_tts")
    logger.setLevel(logging.DEBUG)
    # Remove existing handlers to avoid duplication
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(request_id)s] %(levelname)s: %(message)s"
        )
        handler.setFormatter(formatter)
        handler.addFilter(RequestIdFilter())
        logger.addHandler(handler)
    return logger


logger = setup_logging()
