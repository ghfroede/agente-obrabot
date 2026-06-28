"""RQ job entrypoints."""

from src.worker.index import process_task

__all__ = ["process_task"]
