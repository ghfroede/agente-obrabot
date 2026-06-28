from __future__ import annotations

import asyncio
import signal
import sys
import uuid
from datetime import UTC, datetime

from src.agent.ceo import run_ceo_pipeline
from src.db.client import SyncSessionLocal
from src.db.models import Task, TaskStatus


def _safe_error(exc: Exception) -> str:
    return str(exc)[:500]


def process_task(task_id: str) -> None:
    session = SyncSessionLocal()
    try:
        task = session.get(Task, uuid.UUID(task_id))
        if task is None:
            return

        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.now(UTC)
        session.commit()

        result = asyncio.run(run_ceo_pipeline(task.input))

        task.status = TaskStatus.COMPLETED
        task.result = result
        task.finished_at = datetime.now(UTC)
        task.error = None
        session.commit()
    except Exception as exc:
        session.rollback()
        task = session.get(Task, uuid.UUID(task_id))
        if task is not None:
            task.status = TaskStatus.FAILED
            task.error = _safe_error(exc)
            task.finished_at = datetime.now(UTC)
            session.commit()
        raise
    finally:
        session.close()


def main() -> None:
    from redis import Redis
    from rq import Worker

    from src.config.env import get_settings

    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)

    def handle_sigterm(_signum: int, _frame: object) -> None:
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    worker = Worker(["obrabot"], connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
