"""RQ job entrypoints."""

from src.worker.index import process_entrada, process_task

__all__ = ["process_entrada", "process_task"]
