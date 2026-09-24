import json
import logging
import sys

import pytest

from sonora.logs import (
    AccessLogRedactFilter,
    JsonFormatter,
    RequestIdFilter,
    configure_logging,
    redact,
    request_id_var,
)

TOKEN = "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZg"


def test_redacts_share_tokens() -> None:
    assert redact(f"GET /api/v1/public/shares/{TOKEN}/quiz/check") == (
        "GET /api/v1/public/shares/[redacted]/quiz/check"
    )
    assert redact(f"/share/{TOKEN}") == "/share/[redacted]"
    assert redact("/api/v1/sessions/123") == "/api/v1/sessions/123"


def test_access_log_filter_rewrites_arguments() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s"',
        ("1.2.3.4", "GET", f"/share/{TOKEN}"),
        None,
    )
    assert AccessLogRedactFilter().filter(record)
    assert TOKEN not in record.getMessage()


def test_json_formatter_includes_request_id_and_exceptions() -> None:
    token = request_id_var.set("req-42")
    try:
        record = logging.LogRecord("sonora", logging.ERROR, __file__, 1, "failed %s", ("x",), None)
        RequestIdFilter().filter(record)
        try:
            raise ValueError("boom")
        except ValueError:
            record.exc_info = sys.exc_info()
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["msg"] == "failed x"
    assert payload["request_id"] == "req-42"
    assert payload["level"] == "ERROR"
    assert "ValueError: boom" in payload["exc"]


@pytest.mark.parametrize("json_output", [True, False])
def test_configure_logging_installs_one_handler(json_output: bool) -> None:
    root = logging.getLogger()
    previous = root.handlers[:], root.level
    try:
        configure_logging("debug", json_output=json_output)
        configure_logging("debug", json_output=json_output)
        assert len(root.handlers) == 1
        assert root.level == logging.DEBUG
        assert isinstance(root.handlers[0].formatter, JsonFormatter) is json_output
        access_filters = logging.getLogger("uvicorn.access").filters
        assert sum(isinstance(f, AccessLogRedactFilter) for f in access_filters) == 1
    finally:
        root.handlers[:], _ = previous
        root.setLevel(previous[1])
