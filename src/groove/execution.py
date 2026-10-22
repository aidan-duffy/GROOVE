"""Logging and scoped strict-error policy for CLI and embedded workflows."""
from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_STRICT: ContextVar[bool] = ContextVar("groove_strict", default=False)


def is_strict() -> bool:
    return _STRICT.get()


@contextmanager
def error_policy(strict: bool = False) -> Iterator[None]:
    """Re-raise caught stage errors within this scope, including nested calls."""
    token = _STRICT.set(strict or is_strict())
    try:
        yield
    finally:
        _STRICT.reset(token)


def report_exception(error: Exception, module: str) -> None:
    """Record the exception type/message before fallback, or propagate in strict mode."""
    logging.getLogger(module).warning("%s: %s", type(error).__name__, error)
    if is_strict():
        raise error


def log_info(module: str, *values: Any, sep: str = " ", end: str = "\n", file: Any = None,
             flush: bool = False) -> None:
    """Route former console messages through the package logging hierarchy."""
    message = sep.join(str(value) for value in values)
    logger = logging.getLogger(module)
    (logger.error if file is sys.stderr else logger.info)(message)
