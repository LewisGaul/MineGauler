"""
utils.py - Utils for the IT

February 2020, Lewis Gaul
"""

__all__ = ("ITBase", "process_events", "run_minegauler__main__")

import logging
import os
import time
from importlib.util import find_spec
from types import ModuleType
from unittest import mock

from PyQt5.QtWidgets import QApplication
from tests.utils import activate_patches

from minegauler import core, frontend


logger = logging.getLogger(__name__)


try:
    _EVENT_PAUSE = float(os.environ["TEST_IT_EVENT_WAIT"])
except KeyError:
    _EVENT_PAUSE = 0


def run_minegauler__main__() -> ModuleType:
    """
    Run minegauler via the __main__ module without entering the event loop.

    :return:
        The __main__ module namespace.
    """
    module = ModuleType("minegauler.__main__")
    spec = find_spec("minegauler.__main__")

    def run_app(gui: frontend.MinegaulerGUI) -> int:
        logger.info("In run_app()")
        gui.show()
        return 0

    logger.info("Executing __main__ without starting app event loop")
    with activate_patches(
        [
            mock.patch("minegauler.frontend.run_app", run_app),
            mock.patch("sys.exit"),
            mock.patch("minegauler.shared.write_settings_to_file"),
            mock.patch("minegauler.shared.highscores.insert_highscore"),
        ]
    ):
        spec.loader.exec_module(module)

    return module


def process_events(wait: float = _EVENT_PAUSE) -> None:
    """
    Manually process Qt events (normally taken care of by the event loop).

    The environment variable TEST_IT_EVENT_WAIT can be used to set the
    amount of time to spend processing events (in seconds).
    """
    logger.debug("Processing Qt events (pause of %.2fs)", wait)
    start_time = time.time()
    while QApplication.hasPendingEvents() or time.time() - start_time < wait:
        QApplication.processEvents()


class ITBase:
    """Base class for IT, setting up the app."""

    main_module: ModuleType
    ctrlr: core.BaseController
    gui: frontend.MinegaulerGUI

    @classmethod
    def setup_class(cls):
        """Set up the app to be run using manual processing of events."""
        cls.main_module = run_minegauler__main__()

        cls.ctrlr = cls.main_module.ctrlr
        cls.gui = cls.main_module.gui

    @classmethod
    def teardown_class(cls):
        """Undo class setup."""
        cls.gui.close()
