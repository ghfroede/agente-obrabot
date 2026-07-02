from __future__ import annotations

import logging
import signal
import sys

from src.config.env import get_settings
from src.core.logging import setup_logging
from src.core.redis import get_redis
from src.services.entrada_service import run_entrada_pipeline

logger = logging.getLogger(__name__)


def process_entrada(entrada_id: str) -> None:
    """RQ job: processamento unificado de qualquer canal (api/telegram/openclaw)."""
    import asyncio

    logger.info("rq job process_entrada started", extra={"entrada_id": entrada_id})
    try:
        asyncio.run(run_entrada_pipeline(entrada_id))
        logger.info("rq job process_entrada finished", extra={"entrada_id": entrada_id})
    except Exception:
        logger.exception("rq job process_entrada failed", extra={"entrada_id": entrada_id})
        raise


def main() -> None:
    from rq import Worker

    settings = get_settings()
    setup_logging(is_production=settings.is_production)
    logger.info("worker starting queue=obrabot")
    redis_conn = get_redis()

    def handle_sigterm(_signum: int, _frame: object) -> None:
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    worker = Worker(["obrabot"], connection=redis_conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
