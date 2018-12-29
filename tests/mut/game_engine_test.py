"""
game_engine_test.py - Test the game engine module

October 2018, Lewis Gaul

Uses pytest - simply run 'python -m pytest tests/ [-k game_engine_test]' from
the root directory.
"""


import pytest
from unittest.mock import Mock

from minegauler.backend.game_engine import (Controller, GameOptsStruct,
    _ignore_if, _ignore_if_not)
from minegauler.backend.minefield import Minefield
from minegauler.backend.utils import Board
from minegauler.shared.internal_types import *


@pytest.fixture()
def frontend1():
    return Mock()

@pytest.fixture()
def frontend2():
    return Mock()


class TestController:

    mf = Minefield.from_2d_array([
        [0, 0, 1, 2],
        [0, 0, 0, 1],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 1, 0, 0],
    ])
    opts = GameOptsStruct(x_size=mf.x_size, y_size=mf.y_size, mines=mf.mines,
                          per_cell=mf.per_cell, first_success=True)

    # --------------------------------------------------------------------------
    # Test cases
    # -------------------------------------------------------------------------
    def test_create(self):
        # Normal create of a controller.
        ctrlr = Controller(self.opts)
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.opts == self.opts
        for opt in ['x_size', 'y_size', 'mines', 'per_cell']:
            assert getattr(ctrlr.mf, opt) == getattr(self.opts, opt)
        assert not ctrlr.mf.is_created
        assert ctrlr.board == Board(self.opts.x_size, self.opts.y_size)

        # Try creating a controller with invalid options.
        with pytest.raises(ValueError):
            Controller('INVALID')

    def test_register_callbacks(self, frontend1, frontend2):
        # Register two valid callback functions.
        ctrlr = self.create_controller()
        ctrlr.register_callback(lambda x: None)
        ctrlr.register_callback(lambda x, y=None: None)
        assert len(ctrlr._registered_callbacks) == 2

        # Register an invalid callback - not callable.
        ctrlr = self.create_controller()
        ctrlr.register_callback('NOT CALLABLE')
        #@@@LG Check an error is logged.
        assert len(ctrlr._registered_callbacks) == 0

        # Register an invalid callback - doesn't take a positional argument.
        ctrlr = self.create_controller()
        ctrlr.register_callback(lambda: None)
        #@@@LG Check an error is logged.
        assert len(ctrlr._registered_callbacks) == 0

        # Register an invalid callback - expects too many positional arguments.
        ctrlr = self.create_controller()
        ctrlr.register_callback(lambda x, y: None)
        #@@@LG Check an error is logged.
        assert len(ctrlr._registered_callbacks) == 0

        # Register a callback that can't be inspected.
        ctrlr = self.create_controller()
        ctrlr.register_callback(min)
        #@@@LG Check a warning is logged.
        assert len(ctrlr._registered_callbacks) == 1

        # Check callbacks are called.
        ctrlr = self.create_controller()
        ctrlr._cell_updates = 'dummy'
        ctrlr._registered_callbacks = [frontend1, frontend2]
        ctrlr._send_callback_updates()
        for cb in ctrlr._registered_callbacks:
            cb.assert_called_once()
            cb.reset_mock()

        # Check an error is logged when a callback raises an error.
        frontend1.side_effect = Exception
        ctrlr._cell_updates = 'dummy'
        ctrlr._send_callback_updates()
        #@@@LG Check error is logged.
        for cb in ctrlr._registered_callbacks:
            cb.assert_called_once()
            cb.reset_mock()

    def test_cell_interaction(self, frontend1):
        coord = (2, 2)
        def check_and_reset_callback(cb, ctrlr):
            """Check callback updates match controller's properties."""
            self.check_and_reset_callback(
                cb,
                cells={coord: ctrlr.board[coord]},
                game_state=ctrlr.game_state,
                mines_remaining=ctrlr.mines_remaining)

        # Setup.
        opts = GameOptsStruct(per_cell=2, first_success=False)
        ctrlr = self.create_controller(opts=opts, set_mf=False, cb=frontend1)
        frontend1.assert_not_called()

        # Flag a cell.
        ctrlr.flag_cell(coord)
        assert ctrlr.board[coord] == CellFlag(1)
        assert not ctrlr.mf.is_created
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.mines_remaining == ctrlr.opts.mines - 1
        check_and_reset_callback(frontend1, ctrlr)

        # Select a flagged cell.
        ctrlr.select_cell(coord)
        assert ctrlr.board[coord] == CellFlag(1)
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.mines_remaining == ctrlr.opts.mines - 1
        frontend1.assert_not_called()

        # Flag a cell that is already flagged (multiple mines per cell).
        ctrlr.flag_cell(coord)
        assert ctrlr.board[coord] == CellFlag(2)
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.mines_remaining == ctrlr.opts.mines - 2
        check_and_reset_callback(frontend1, ctrlr)

        # Flag a cell that is at max flags to reset it.
        ctrlr.flag_cell(coord)
        assert ctrlr.board[coord] == CellUnclicked()
        assert not ctrlr.mf.is_created
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.mines_remaining == ctrlr.opts.mines
        check_and_reset_callback(frontend1, ctrlr)

        # Remove cell flags.
        ctrlr.flag_cell(coord)
        frontend1.reset_mock()
        ctrlr.remove_cell_flags(coord)
        assert ctrlr.board[coord] == CellUnclicked()
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.mines_remaining == ctrlr.opts.mines
        check_and_reset_callback(frontend1, ctrlr)

        # Select a cell to start the game.
        ctrlr.select_cell(coord)
        assert isinstance(ctrlr.board[coord], (CellHitMine, CellNum))
        assert ctrlr.mf.is_created
        assert ctrlr.game_state in {GameState.ACTIVE, GameState.LOST}
        assert ctrlr.mines_remaining == ctrlr.opts.mines
        self.check_and_reset_callback(frontend1, game_state=ctrlr.game_state)

        # Select an already-selected cell.
        revealed = ctrlr.board[coord]
        ctrlr.select_cell(coord)
        assert ctrlr.board[coord] == revealed
        frontend1.assert_not_called()

    def test_select_opening(self, frontend1):
        exp_board = Board.from_2d_array([
            [ 0 ,  1 , '#', '#'],
            [ 0 ,  1 ,  4 , '#'],
            [ 0 ,  0 ,  1 , '#'],
            [ 1 ,  1 ,  1 , '#'],
            ['#', '#', '#', '#'],
        ])
        # Select a cell to trigger the opening.
        ctrlr = self.create_controller(cb=frontend1)
        ctrlr.select_cell((0, 0))
        assert ctrlr.board == exp_board
        self.check_and_reset_callback(frontend1, game_state=GameState.ACTIVE)

        # Select the edge of an opening.
        ctrlr = self.create_controller()
        ctrlr.select_cell((1, 3))
        assert ctrlr.board ==  Board.from_2d_array([
            ['#', '#', '#', '#'],
            ['#', '#', '#', '#'],
            ['#', '#', '#', '#'],
            ['#',  1 , '#', '#'],
            ['#', '#', '#', '#'],
        ])

        # Select a different cell to trigger the same opening as above.
        ctrlr.select_cell((1, 2))
        assert ctrlr.board == exp_board

        # Select another cell to trigger the other opening.
        ctrlr.select_cell((3, 4))
        assert ctrlr.board ==  Board.from_2d_array([
            [ 0,   1 , '#', '#'],
            [ 0,   1 ,  4 , '#'],
            [ 0,   0 ,  1 ,  1 ],
            [ 1,   1 ,  1 ,  0 ],
            ['#', '#',  1 ,  0 ],
        ])

        # Trigger opening with incorrect flag blocking the way.
        ctrlr = self.create_controller()
        ctrlr.flag_cell((0, 1))
        ctrlr.select_cell((0, 0))
        assert ctrlr.board == Board.from_2d_array([
            [  0 ,  1 , '#', '#'],
            ['F1',  1 , '#', '#'],
            [ '#', '#', '#', '#'],
            [ '#', '#', '#', '#'],
            [ '#', '#', '#', '#'],
        ])

        # Select doesn't trigger remainder of opening on revealed opening.
        ctrlr.remove_cell_flags((0, 1))
        ctrlr.select_cell((0, 0))
        assert ctrlr.board == Board.from_2d_array([
            [ 0 ,  1 , '#', '#'],
            ['#',  1 , '#', '#'],
            ['#', '#', '#', '#'],
            ['#', '#', '#', '#'],
            ['#', '#', '#', '#'],
        ])

        # Chording does trigger remainder of opening on revealed opening. Also
        #  test other invalid flags blocking the opening.
        ctrlr.flag_cell((0, 3))
        ctrlr.flag_cell((0, 2))
        ctrlr.chord_on_cell((0, 0))
        assert ctrlr.board == Board.from_2d_array([
            [  0 ,  1 , '#', '#'],
            [  0 ,  1 ,  4 , '#'],
            ['F1',  0 ,  1 , '#'],
            ['F1',  1 ,  1 , '#'],
            [ '#', '#', '#', '#'],
        ])

    def test_chording(self, frontend1):
        # Use the same controller throughout the test.

        # No-op chording - game not started.
        ctrlr = self.create_controller(cb=frontend1)
        ctrlr.chord_on_cell((0, 0))
        assert ctrlr.game_state == GameState.READY
        frontend1.assert_not_called()

        # No-op chording - no flags.
        ctrlr.select_cell((0, 4))
        frontend1.reset_mock()
        ctrlr.chord_on_cell((0, 4))
        assert ctrlr.board ==  Board.from_2d_array([
            ['#', '#', '#', '#'],
            ['#', '#', '#', '#'],
            ['#', '#', '#', '#'],
            ['#', '#', '#', '#'],
            [ 1,  '#', '#', '#'],
        ])
        frontend1.assert_not_called()

        # Basic successful chording.
        ctrlr.flag_cell((1, 4))
        frontend1.reset_mock()
        ctrlr.chord_on_cell((0, 4))
        assert ctrlr.board ==  Board.from_2d_array([
            ['#',  '#', '#', '#'],
            ['#',  '#', '#', '#'],
            ['#',  '#', '#', '#'],
            [ 1 ,   1 , '#', '#'],
            [ 1 , 'F1', '#', '#'],
        ])
        self.check_and_reset_callback(
            frontend1,
            cells={c: CellNum(1) for c in [(0, 3), (1, 3)]},
            game_state=GameState.ACTIVE)

        # Successful chording triggering opening.
        ctrlr.chord_on_cell((1, 3))
        assert ctrlr.board ==  Board.from_2d_array([
            [ 0,   1 , '#', '#'],
            [ 0,   1 ,  4 , '#'],
            [ 0,   0 ,  1 , '#'],
            [ 1,   1 ,  1 , '#'],
            [ 1, 'F1',  1 , '#'],
        ])
        self.check_and_reset_callback(frontend1)

        # No-op - repeated chording.
        prev_board = ctrlr.board
        ctrlr.chord_on_cell((1, 3))
        assert ctrlr.board == prev_board
        frontend1.assert_not_called()

        # No-op - chording on flagged cell.
        ctrlr.chord_on_cell((1, 4))
        assert ctrlr.board == prev_board
        frontend1.assert_not_called()

        # No-op - wrong number of flags.
        ctrlr.flag_cell((3, 0))
        ctrlr.flag_cell((3, 0))
        frontend1.reset_mock()
        ctrlr.chord_on_cell((2, 1))
        frontend1.assert_not_called()

        # Incorrect flags cause hitting a mine.
        ctrlr.flag_cell((3, 2))
        frontend1.reset_mock()
        ctrlr.chord_on_cell((2, 2))
        assert ctrlr.board ==  Board.from_2d_array([
            [ 0,   1 , 'M1', 'F2'],
            [ 0,   1 ,   4 , '!1'],
            [ 0,   0 ,   1 , 'X1'],
            [ 1,   1 ,   1 ,   0 ],
            [ 1, 'F1',   1 ,   0 ],
        ])
        self.check_and_reset_callback(frontend1, game_state=GameState.LOST)

    def test_first_success(self):
        # First click should hit an opening with first_success set.
        opts = GameOptsStruct(first_success=True)
        ctrlr = Controller(opts)
        coord = (1, 5)
        ctrlr.select_cell(coord)
        assert ctrlr.game_state == GameState.ACTIVE
        assert ctrlr.board[coord] == CellNum(0)
        for c in ctrlr.board.get_nbrs(coord):
            assert type(ctrlr.board[c]) == CellNum

        # Check first success is ignored when using created minefield.
        ctrlr = self.create_controller()
        coord = (3, 0)
        ctrlr.select_cell(coord)
        assert ctrlr.game_state == GameState.LOST
        assert ctrlr.board[coord] == CellHitMine(2)

        # Test first success on a high density board - no room for opening.
        opts = GameOptsStruct(x_size=4, y_size=4, mines=15, per_cell=1,
                              first_success=True)
        ctrlr = Controller(opts)
        coord = (1, 2)
        ctrlr.select_cell(coord)
        assert ctrlr.board[coord] == CellNum(8)

        # Test first success turned off - should hit a mine with high density.
        opts.first_success = False
        passed = False
        attempts = 0
        while not passed:
            ctrlr = Controller(opts)
            ctrlr.select_cell(coord)
            attempts += 1
            if attempts >= 10:
                assert ctrlr.board[coord] == CellHitMine(1)
            elif ctrlr.board[coord] == CellHitMine(1):
                passed = True

    def test_losing(self, frontend1):
        # Lose straight away.
        ctrlr = self.create_controller(cb=frontend1)
        ctrlr.select_cell((3, 0))
        assert ctrlr.game_state == GameState.LOST
        assert ctrlr.end_time is not None
        assert ctrlr.board == Board.from_2d_array([
            ['#',  '#', 'M1', '!2'],
            ['#',  '#',  '#', 'M1'],
            ['#',  '#',  '#',  '#'],
            ['#',  '#',  '#',  '#'],
            ['#', 'M1',  '#',  '#'],
        ])
        self.check_and_reset_callback(
            frontend1,
            cells={(2, 0): CellMine(1), (3, 0): CellHitMine(2),
                   (3, 1): CellMine(1), (1, 4): CellMine(1)},
            game_state=GameState.LOST,
            mines_remaining=ctrlr.opts.mines)

        # Lose after game has been started with incorrect flag.
        ctrlr = self.create_controller(cb=frontend1)
        ctrlr.select_cell((1, 0))
        ctrlr.flag_cell((1, 1))
        frontend1.reset_mock()
        ctrlr.select_cell((2, 0))
        assert ctrlr.game_state == GameState.LOST
        assert ctrlr.board == Board.from_2d_array([
            ['#',   1 , '!1', 'M2'],
            ['#', 'X1',  '#', 'M1'],
            ['#',  '#',  '#',  '#'],
            ['#',  '#',  '#',  '#'],
            ['#', 'M1',  '#',  '#'],
        ])
        self.check_and_reset_callback(frontend1)

        # Check cells can't be selected when the game is lost.
        for c in ctrlr.board.all_coords:
            ctrlr.select_cell(c)
            ctrlr.flag_cell(c)
            ctrlr.chord_on_cell(c)
            ctrlr.remove_cell_flags(c)
        assert ctrlr.game_state == GameState.LOST
        frontend1.assert_not_called()

        # Check losing via chording works.
        ctrlr = self.create_controller()
        ctrlr.select_cell((1, 0))
        ctrlr.flag_cell((1, 1))
        ctrlr.chord_on_cell((1, 0))
        assert ctrlr.game_state == GameState.LOST
        assert ctrlr.board == Board.from_2d_array([
            [ 0 ,   1 , '!1', 'M2'],
            [ 0 , 'X1',   4 , 'M1'],
            [ 0 ,   0 ,   1 ,  '#'],
            [ 1 ,   1 ,   1 ,  '#'],
            ['#', 'M1',  '#',  '#'],
        ])

    def test_winning(self, frontend1):
        # Test winning in one click.
        opts = GameOptsStruct(x_size=2, y_size=1, mines=1, first_success=True)
        ctrlr = self.create_controller(opts=opts, set_mf=False, cb=frontend1)
        ctrlr.select_cell((0, 0))
        assert ctrlr.game_state == GameState.WON
        assert ctrlr.end_time is not None
        assert ctrlr.mines_remaining == 0
        assert ctrlr.board == ctrlr.mf.completed_board
        self.check_and_reset_callback(
            frontend1,
            cells={(0, 0): CellNum(1), (1, 0): CellFlag(1)},
            game_state=GameState.WON,
            mines_remaining=0)

        # Check winning via chording and hitting an opening works.
        ctrlr = self.create_controller()
        ctrlr.select_cell((0, 0))
        ctrlr.select_cell((0, 4))
        ctrlr.flag_cell((3, 1))
        ctrlr.chord_on_cell((2, 2))
        assert ctrlr.game_state == GameState.WON
        assert ctrlr.board == ctrlr.mf.completed_board == Board.from_2d_array([
            [ 0,   1 , 'F1', 'F2'],
            [ 0,   1 ,   4 , 'F1'],
            [ 0,   0 ,   1 ,   1 ],
            [ 1,   1 ,   1 ,   0 ],
            [ 1, 'F1',   1,    0 ],
        ])

        # Check cells can't be selected when the game is won.
        for c in ctrlr.board.all_coords:
            ctrlr.select_cell(c)
            ctrlr.flag_cell(c)
            ctrlr.chord_on_cell(c)
            ctrlr.remove_cell_flags(c)
        assert ctrlr.game_state == GameState.WON
        frontend1.assert_not_called()

    def test_new_game(self, frontend1):
        """Only require a single controller when able to create new games."""
        ctrlr = self.create_controller(cb=frontend1)

        # Start a new game before doing anything else with minefield.
        assert ctrlr.mf.is_created
        ctrlr.new_game()
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.board == Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        assert not ctrlr.mf.is_created
        frontend1.assert_not_called()

        # Start a new game that isn't started but has flags.
        ctrlr.flag_cell((0, 0))
        ctrlr.flag_cell((1, 0))
        ctrlr.flag_cell((1, 0))
        assert ctrlr.board != Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        frontend1.reset_mock()
        ctrlr.new_game()
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.mines_remaining == ctrlr.opts.mines
        assert ctrlr.board == Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        self.check_and_reset_callback(
            frontend1,
            cells={(0, 0): CellUnclicked(), (1, 0): CellUnclicked()},
            mines_remaining=ctrlr.opts.mines)

        # Start a new game mid-game.
        ctrlr.select_cell((0, 0))
        ctrlr.select_cell((0, 1))
        assert ctrlr.game_state == GameState.ACTIVE
        assert ctrlr.mf.is_created
        assert ctrlr.board != Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        frontend1.reset_mock()
        ctrlr.new_game()
        assert ctrlr.game_state == GameState.READY
        assert not ctrlr.mf.is_created
        assert ctrlr.start_time is None
        assert ctrlr.mines_remaining == ctrlr.opts.mines
        assert ctrlr.board == Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        self.check_and_reset_callback(frontend1)

        # Start a new game on lost game.
        ctrlr.mf = self.mf
        ctrlr.select_cell((3, 0))
        assert ctrlr.game_state == GameState.LOST
        assert ctrlr.mf.is_created
        assert ctrlr.board != Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        frontend1.reset_mock()
        ctrlr.new_game()
        assert ctrlr.game_state == GameState.READY
        assert not ctrlr.mf.is_created
        assert ctrlr.start_time is ctrlr.end_time is None
        assert ctrlr.mines_remaining == ctrlr.opts.mines
        assert ctrlr.board == Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        self.check_and_reset_callback(
            frontend1,
            cells={c: CellUnclicked() for c in ctrlr.mf.all_coords
                   if ctrlr.mf.cell_contains_mine(c)},
            mines_remaining=ctrlr.opts.mines)

    def test_restart_game(self, frontend1):
        """Only require a single controller."""
        ctrlr = self.create_controller(set_mf=False, cb=frontend1)

        # Replay before doing anything else, without minefield.
        ctrlr.restart_game()
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.board == Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        assert not ctrlr.mf.is_created
        frontend1.assert_not_called()

        # Replay before doing anything else, with minefield.
        ctrlr.mf = self.mf
        ctrlr.restart_game()
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.board == Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        assert ctrlr.mf == self.mf
        frontend1.assert_not_called()

        # Restart a game that isn't started but has flags.
        ctrlr.flag_cell((0, 0))
        ctrlr.flag_cell((1, 0))
        ctrlr.flag_cell((1, 0))
        frontend1.reset_mock()
        ctrlr.restart_game()
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.mines_remaining == ctrlr.opts.mines
        assert ctrlr.board == Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        assert ctrlr.mf == self.mf
        self.check_and_reset_callback(
            frontend1,
            cells={(0, 0): CellUnclicked(), (1, 0): CellUnclicked()},
            mines_remaining=ctrlr.opts.mines)

        # Restart game mid-game.
        ctrlr.select_cell((0, 0))
        assert ctrlr.game_state == GameState.ACTIVE
        frontend1.reset_mock()
        opened_cells = (c for c in ctrlr.mf.all_coords
                        if ctrlr.board[c] != CellUnclicked())
        ctrlr.restart_game()
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.start_time is None
        assert ctrlr.board == Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        assert ctrlr.mf == self.mf
        self.check_and_reset_callback(
            frontend1,
            cells={c: CellUnclicked() for c in opened_cells},
            mines_remaining=ctrlr.opts.mines,
            game_state=GameState.READY)

        # Restart finished game (lost game).
        ctrlr.select_cell((3, 0))
        assert ctrlr.game_state == GameState.LOST
        frontend1.reset_mock()
        ctrlr.restart_game()
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.start_time is ctrlr.end_time is None
        assert ctrlr.mines_remaining == ctrlr.opts.mines
        assert ctrlr.board == Board(ctrlr.opts.x_size, ctrlr.opts.y_size)
        assert ctrlr.mf == self.mf
        self.check_and_reset_callback(frontend1)

    def test_resize_board(self, frontend1):
        # Setup, including start a game.
        opts = self.opts.copy()
        ctrlr = self.create_controller(opts=opts, cb=frontend1)
        ctrlr.select_cell((0, 0))
        ctrlr.flag_cell((2, 0))
        assert ctrlr.game_state == GameState.ACTIVE
        assert ctrlr.mines_remaining == opts.mines - 1
        frontend1.reset_mock()

        # Normal resize.
        opts.x_size, opts.y_size, opts.mines = 10, 2, 3
        ctrlr.resize_board(x_size=opts.x_size, y_size=opts.y_size,
                           mines=opts.mines)
        assert ctrlr.opts == opts
        for opt in ['x_size', 'y_size', 'mines']:
            assert getattr(ctrlr.mf, opt) == getattr(opts, opt)
        assert ctrlr.game_state == GameState.READY
        assert ctrlr.mines_remaining == ctrlr.opts.mines
        assert not ctrlr.mf.is_created
        assert ctrlr.board == Board(opts.x_size, opts.y_size)
        frontend1.assert_not_called()

        # Resize without changing values starts new game.
        ctrlr.select_cell((0, 0))
        assert ctrlr.game_state == GameState.ACTIVE
        frontend1.reset_mock()
        ctrlr.resize_board(x_size=opts.x_size, y_size=opts.y_size,
                           mines=opts.mines)
        assert ctrlr.game_state == GameState.READY
        assert not ctrlr.mf.is_created
        assert ctrlr.board == Board(opts.x_size, opts.y_size)
        frontend1.assert_not_called()

    def test_invalid_game_state(self, frontend1):
        # Use one controller throughout.
        ctrlr = self.create_controller(cb=frontend1)

        # New game - should work.
        ctrlr.select_cell((0, 0))
        frontend1.reset_mock()
        ctrlr.game_state = GameState.INVALID
        ctrlr.new_game()
        assert ctrlr.game_state == GameState.READY
        self.check_and_reset_callback(frontend1, game_state=GameState.READY)

        # Restart game (no-op).
        ctrlr.select_cell((1, 0))
        ctrlr.flag_cell((2, 0))
        frontend1.reset_mock()
        ctrlr.game_state = GameState.INVALID
        ctrlr.restart_game()
        assert ctrlr.game_state == GameState.INVALID
        frontend1.assert_not_called()

        # Select cell (no-op).
        ctrlr.select_cell((0, 0))
        frontend1.assert_not_called()

        # Flag cell (no-op).
        ctrlr.flag_cell((0, 0))
        frontend1.assert_not_called()

        # Chord on cell (no-op).
        ctrlr.chord_on_cell((1, 0))
        frontend1.assert_not_called()

    def test_ignore_if_decorators(self):
        """
        Test the 'ignore if' and 'ignore if not' decorators, since they aren't
        fully used in the code.
        """
        ctrlr = self.create_controller()
        mock = Mock()

        ## First test 'ignore if'.
        # Test with one ignored cell state (flagged).
        decorated_mock = _ignore_if(cell_state=CellFlag)(mock)
        decorated_mock(ctrlr, (0, 0))  # unclicked
        mock.assert_called_once()
        mock.reset_mock()

        ctrlr.flag_cell((0, 0))
        decorated_mock(ctrlr, (0, 0))  # flagged
        mock.assert_not_called()

        # Test with multiple ignored cell states.
        decorated_mock = _ignore_if(cell_state=(CellFlag, CellUnclicked))(mock)
        decorated_mock(ctrlr, (0, 0))  # flagged
        mock.assert_not_called()

        decorated_mock(ctrlr, (0, 1))  # unclicked
        mock.assert_not_called()

        ## Next test 'ignore if not'.
        mock.reset_mock()
        # Test with one game state (READY).
        decorated_mock = _ignore_if_not(game_state=GameState.READY)(mock)
        ctrlr.game_state = GameState.READY
        decorated_mock(ctrlr)
        mock.assert_called_once()
        mock.reset_mock()

        ctrlr.game_state = GameState.ACTIVE
        decorated_mock(ctrlr)
        mock.assert_not_called()

        # Test with multiple ignored cell states.
        decorated_mock = _ignore_if_not(game_state=(GameState.READY,
                                                    GameState.ACTIVE))(mock)
        ctrlr.game_state = GameState.READY
        decorated_mock(ctrlr)
        mock.assert_called_once()
        mock.reset_mock()

        ctrlr.game_state = GameState.ACTIVE
        decorated_mock(ctrlr)
        mock.assert_called_once()
        mock.reset_mock()

        ctrlr.game_state = GameState.LOST
        decorated_mock(ctrlr)
        mock.assert_not_called()

    # --------------------------------------------------------------------------
    # Helper methods
    # --------------------------------------------------------------------------
    @classmethod
    def create_controller(cls, *, opts=None, set_mf=True, cb=None):
        """
        Convenience method for creating a controller instance. Uses the test
        class options and minefield by default, and registers a callback if one
        is given.

        Arguments:
        opts=None
            Optionally override the default options.
        set_mf=True
            Whether to set the minefield or leave it not being created.
        cb=None
            Optionally specify a callback to register.
        """
        if opts is None:
            opts = cls.opts
        ctrlr = Controller(opts)
        if set_mf:
            ctrlr.mf = cls.mf
        if cb:
            ctrlr._registered_callbacks = [cb]

        return ctrlr

    @staticmethod
    def check_and_reset_callback(cb, *,
                                 cells=None, game_state=None,
                                 mines_remaining=None):
        """
        Assert that a callback was called exactly once, and with information
        matching whatever is passed in to this method.
        """
        cb.assert_called_once()
        passed_info = cb.call_args[0][0]
        if cells:
            assert passed_info.cell_updates == cells
        if game_state:
            assert passed_info.game_state == game_state
        if mines_remaining is not None:
            assert passed_info.mines_remaining == mines_remaining
        cb.reset_mock()