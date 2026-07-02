from __future__ import annotations

import json
import logging
import logging.config
import sys
from datetime import UTC, datetime

_LOG_RECORD_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "thread",
        "threadName",
        "taskName",
        "exc_info",
        "exc_text",
        "stack_info",
    }
)

_configured = False


class JsonFormatter(logging.Formatter):
    """Formata logs em JSON (produção) com campos extras de contexto."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(*, is_production: bool) -> None:
    """Configura logging centralizado (JSON em produção, legível em dev)."""
    global _configured
    if _configured:
        return

    level = "INFO" if is_production else "DEBUG"
    formatter_name = "json" if is_production else "console"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {"()": "src.core.logging.JsonFormatter"},
                "console": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                    "datefmt": "%H:%M:%S",
                },
            },
            "handlers": {
                "stderr": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                    "formatter": formatter_name,
                },
            },
            "root": {"level": level, "handlers": ["stderr"]},
        }
    )
    logging.captureWarnings(True)
    _configured = True

    # Garante que o handler usa stderr mesmo se dictConfig falhar silenciosamente.
    if not logging.getLogger().handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            JsonFormatter() if is_production else logging.Formatter("%(levelname)s %(message)s")
        )
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(level)
