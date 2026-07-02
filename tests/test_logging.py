from __future__ import annotations

import json
import logging

from src.core.logging import JsonFormatter, setup_logging


def test_setup_logging_idempotent() -> None:
    setup_logging(is_production=False)
    setup_logging(is_production=False)
    assert logging.getLogger().handlers


def test_json_formatter_includes_extra_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="pipeline ok",
        args=(),
        exc_info=None,
    )
    record.entrada_id = "abc-123"
    record.obra_id = "OBRA-001"
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "pipeline ok"
    assert payload["entrada_id"] == "abc-123"
    assert payload["obra_id"] == "OBRA-001"
