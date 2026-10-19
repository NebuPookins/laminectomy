"""Logging setup shared by the GUI, the CLI and the extraction worker processes.

Every module logs through ``logging.getLogger(__name__)``. Failures are logged
with their full traceback (``logger.exception``) and are never silently dropped.
Worker processes start with a fresh interpreter, so they call configure_logging
too, through the process pool's initializer.
"""

from __future__ import annotations

import logging
import os
import sys

_FORMAT = "%(asctime)s %(levelname)-7s %(processName)s %(name)s: %(message)s"
_HANDLER_NAME = "laminectomy"


def configure_logging() -> None:
    """Send all log records to stderr. Set LAMINECTOMY_LOG=DEBUG for more detail.

    Calling this more than once is harmless.
    """
    level = os.environ.get("LAMINECTOMY_LOG", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)
    if any(handler.name == _HANDLER_NAME for handler in root.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
