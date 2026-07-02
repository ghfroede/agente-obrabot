from __future__ import annotations

import pytest


def test_process_entrada_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.worker import index as worker_index

    async def _fail(_entrada_id: str) -> dict[str, object]:
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(worker_index, "run_entrada_pipeline", _fail)

    with pytest.raises(RuntimeError, match="pipeline exploded"):
        worker_index.process_entrada("entrada-123")
