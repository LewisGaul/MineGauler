"""
Integration test, aiming to cover all mainline code.

December 2019, Lewis Gaul
"""

import logging

from minegauler import core, frontend

from .utils import ITBase, process_events


logger = logging.getLogger(__name__)


class TestMain(ITBase):
    """Test running minegauler in an IT way."""

    def test_setup(self):
        """Test the setup is sane."""
        assert type(self.ctrlr) is core.BaseController
        assert type(self.gui) is frontend.MinegaulerGUI
        assert self.gui._ctrlr is self.ctrlr

    def test_play_game(self):
        """Test basic playing of a game."""
        process_events()
        self.ctrlr.select_cell((1, 2))
        process_events()
        self.ctrlr.select_cell((6, 4))
        process_events()

    def test_change_board(self):
        """Test changing the board."""
        self.ctrlr.resize_board(40, 1, 1)
        process_events()
