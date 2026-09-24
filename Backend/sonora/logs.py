"""Logging setup.

Plain text for development, JSON lines for production. Every record carries the id of
the request it belongs to, and share tokens are redacted from access-log lines.
"""

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Share links are bearer capabilities; keep them out of logs.
_SHARE_TOKEN_RE = re.compile(r"(/shares?/)[A-Za-z0-9_-]{16,}")


def redact(text: str) -> str:
    return _SHARE_TOKEN_RE.sub(r"\1[redacted]", text)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class AccessLogRedactFilter(logging.Filter):
    """Redacts share tokens from uvicorn access-log arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        JsonFormatter()
        if json_output
        else logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessLogRedactFilter) for f in access.filters):
        access.addFilter(AccessLogRedactFilter())
    for noisy in ("httpx", "httpcore", "faster_whisper", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
