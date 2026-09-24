"""Standalone worker: ``python -m sonora.worker``."""

import asyncio
import contextlib
import signal

from sonora.config import get_settings
from sonora.container import build_services
from sonora.logs import configure_logging
from sonora.worker.runner import Worker


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    services = build_services(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Not supported on Windows, where Ctrl+C raises KeyboardInterrupt instead.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    try:
        await Worker(services).run(stop)
    finally:
        await services.aclose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
