"""Logging that writes to a run log file and, when inside ArcGIS, to the tool
message pane at the same time (scope 6.5).

No arcpy import at module level - the handler probes for it so this module
stays importable in CI.
"""

from __future__ import annotations

import getpass
import logging
import subprocess
from datetime import datetime
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)-18s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ArcpyHandler(logging.Handler):
    """Mirror log records into ArcGIS tool messages.

    Silently no-ops outside ArcGIS so the same code runs from a plain shell.
    """

    def __init__(self) -> None:
        super().__init__()
        try:
            import arcpy  # noqa: F401

            self._arcpy = arcpy
        except ImportError:
            self._arcpy = None

    def emit(self, record: logging.LogRecord) -> None:
        if self._arcpy is None:
            return
        msg = self.format(record)
        try:
            if record.levelno >= logging.ERROR:
                self._arcpy.AddError(msg)
            elif record.levelno >= logging.WARNING:
                self._arcpy.AddWarning(msg)
            else:
                self._arcpy.AddMessage(msg)
        except Exception:  # pragma: no cover - never let logging break a tool
            self.handleError(record)


def make_run_id(scenario: str | None = None) -> str:
    """Run identifier: YYYYMMDD_HHMM[_scenario] (scope 6.5)."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return f"{stamp}_{scenario}" if scenario else stamp


def git_commit(repo_root: Path | str | None = None) -> str:
    """Short git commit hash, or 'nogit' when unavailable.

    Recorded in ScoreRuns so every result traces to the code that produced it.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return out.stdout.strip() or "nogit"
    except Exception:
        return "nogit"


def current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def get_logger(
    name: str = "li",
    log_dir: Path | str | None = None,
    run_id: str | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Configure and return a logger writing to outputs/logs/<run_id>.log."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    arc = ArcpyHandler()
    arc.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(arc)

    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{run_id or make_run_id()}.log"
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
