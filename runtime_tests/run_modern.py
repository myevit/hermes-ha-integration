"""HA 2026.11 test-fixture adapter, not an integration/runtime monkey patch.

The latest published pytest HA plugin still pins 2026.10.4. HA 2026.11 moved
logger overrides from module globals to each logger class's closure. Its old
fixture reset symbol disappeared. Replace ONLY that obsolete test-cleanup
hook with resetting the logger class, and preload HA before HTTPX plugins.
"""
import logging
import sys

import homeassistant
from homeassistant.components import logger

if not hasattr(logger, "_clear_logger_overwrites"):
    def clear_logger_overwrites():
        logging.setLoggerClass(logging.Logger)
    logger._clear_logger_overwrites = clear_logger_overwrites

import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["-c", "runtime_tests/pytest.ini", *sys.argv[1:]]))
