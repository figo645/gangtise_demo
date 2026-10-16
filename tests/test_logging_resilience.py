"""Storage failures must not flood request logs or stop application logging."""

import errno
import io
import logging
from logging.handlers import RotatingFileHandler
from unittest.mock import patch

import pytest

from src.runtime import _ResilientRotatingFileHandler


@pytest.mark.parametrize("failure", [errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EACCES])
def test_file_storage_failure_backs_off_and_recovers(tmp_path, failure):
    path = tmp_path / "app.log"
    handler = _ResilientRotatingFileHandler(path, maxBytes=1024, backupCount=1, delay=True)
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord("test", logging.WARNING, __file__, 1, "business event", (), None)
    console = io.StringIO()
    console_handler = logging.StreamHandler(console)
    diagnostic = io.StringIO()
    try:
        with patch("src.runtime.time.monotonic", return_value=100), patch("src.runtime.sys.stderr", diagnostic), patch.object(
            handler, "shouldRollover", side_effect=OSError(failure, "storage unavailable")
        ) as rollover:
            for _ in range(10):
                handler.handle(record)
                console_handler.handle(record)
        assert rollover.call_count == 1
        assert diagnostic.getvalue().count("File logging unavailable") == 1
        assert "Logging error" not in diagnostic.getvalue()
        assert console.getvalue().count("business event") == 10
        assert handler._retry_at == 160
        with patch("src.runtime.time.monotonic", return_value=160):
            handler.handle(record)
        assert path.read_text() == "business event\n"
    finally:
        handler.close()
        console_handler.close()


def test_unexpected_logging_errors_remain_visible(tmp_path):
    handler = _ResilientRotatingFileHandler(tmp_path / "app.log", delay=True)
    record = logging.LogRecord("test", logging.ERROR, __file__, 1, "error", (), None)
    try:
        with patch.object(handler, "shouldRollover", side_effect=ValueError("unexpected")), patch.object(
            RotatingFileHandler, "handleError"
        ) as normal_error:
            handler.handle(record)
        normal_error.assert_called_once_with(record)
        assert handler._retry_at == 0
    finally:
        handler.close()
