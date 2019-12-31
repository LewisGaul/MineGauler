"""
engine.py - The core game logic

November 2018, Lewis Gaul

Exports:
BaseController (class)
    Implementation of game logic and provision of functions to be called by a
    frontend implementation.
"""

__all__ = ("BaseController", "CreateController", "GameController")

import logging
from typing import Dict, Optional

import attr

from ..shared import utils
from ..types import (
    CellContentsType,
    CellFlag,
    CellMine,
    CellNum,
    CellUnclicked,
    GameState,
    UIMode,
)
from ..typing import Coord_T
from . import api
from . import board as brd
from . import game


logger = logging.getLogger(__name__)


@attr.attrs(auto_attribs=True)
class _SharedInfo:
    """
    Information to pass to frontends.
    
    Elements:
    cell_updates ({(int, int): CellContentsType, ...})
        Dictionary of updates to cells, mapping the coordinate to the new
        contents of the cell.
    game_state (GameState)
        The state of the game.
    mines_remaining (int)
        The number of mines remaining to be found, given by
        [total mines] - [number of flags]. Can be negative if there are too many
        flags. If the number is unchanged, None may be passed.
    lives_remaining (int)
        The number of lives remaining.
    finish_time (float | None)
        The time elapsed if the game has ended, otherwise None.
    """

    cell_updates: Dict[Coord_T, CellContentsType] = attr.Factory(dict)
    game_state: GameState = GameState.READY
    mines_remaining: int = 0
    lives_remaining: int = 0
    end_game_info: Optional[api.EndedGameInfo] = None


class BaseController(api.AbstractSwitchingController):
    """Base controller implementing all user interaction methods."""

    def __init__(
        self, opts: utils.GameOptsStruct, *, notif: Optional[api.Caller] = None
    ):
        super().__init__(opts, notif=notif)
        self._active_ctrlr: api.AbstractController = GameController(
            self._opts, notif=self._notif
        )

    def switch_mode(self, mode: UIMode) -> None:
        """Switch the mode of the UI, e.g. into 'create' mode."""
        super().switch_mode(mode)
        if mode is UIMode.GAME:
            self._active_ctrlr = GameController(self._opts, notif=self._notif)
        elif mode is UIMode.CREATE:
            self._active_ctrlr = CreateController(self._opts, notif=self._notif)
        else:
            raise ValueError(f"Unrecognised UI mode: {mode}")

    # ----------------------------------
    # Delegated abstractmethods
    # ----------------------------------
    @property
    def board(self) -> brd.Board:
        return self._active_ctrlr.board

    def new_game(self) -> None:
        self._active_ctrlr.new_game()

    def restart_game(self) -> None:
        self._active_ctrlr.restart_game()

    def select_cell(self, coord: Coord_T) -> None:
        self._active_ctrlr.select_cell(coord)

    def flag_cell(self, coord: Coord_T, *, flag_only: bool = False) -> None:
        self._active_ctrlr.flag_cell(coord, flag_only=flag_only)

    def chord_on_cell(self, coord: Coord_T) -> None:
        self._active_ctrlr.chord_on_cell(coord)

    def remove_cell_flags(self, coord: Coord_T) -> None:
        self._active_ctrlr.remove_cell_flags(coord)

    def resize_board(self, x_size: int, y_size: int, mines: int) -> None:
        self._opts.x_size = x_size
        self._opts.y_size = y_size
        self._opts.mines = mines
        self._active_ctrlr.resize_board(x_size=x_size, y_size=y_size, mines=mines)

    def set_first_success(self, value: bool) -> None:
        self._opts.first_success = value
        self._active_ctrlr.set_first_success(value)

    def set_per_cell(self, value: int) -> None:
        self._opts.per_cell = value
        self._active_ctrlr.set_per_cell(value)


class GameController(api.AbstractController):
    """
    Class for processing all game logic. Implements functions defined in
    AbstractController that are called from UI.
    
    Attributes:
    opts (GameOptsStruct)
        Options for use in games.
    """

    def __init__(
        self, opts: utils.GameOptsStruct, *, notif: Optional[api.Caller] = None
    ):
        """
        Arguments:
        opts (GameOptsStruct)
            Object containing the required game options as attributes.
        """
        super().__init__(opts, notif=notif)

        self._drag_select = False
        self._name = ""
        self._game = game.Game(
            x_size=self._opts.x_size,
            y_size=self._opts.y_size,
            mines=self._opts.mines,
            per_cell=self._opts.per_cell,
            lives=self._opts.lives,
            first_success=self._opts.first_success,
        )
        self._last_update: _SharedInfo = _SharedInfo()
        self._notif.set_mines(self._opts.mines)
        self._send_reset_update()

    @property
    def board(self) -> brd.Board:
        return self._game.board

    # --------------------------------------------------------------------------
    # Methods triggered by user interaction
    # --------------------------------------------------------------------------
    def new_game(self) -> None:
        """See AbstractController."""
        super().new_game()
        self._game = game.Game(
            x_size=self._opts.x_size,
            y_size=self._opts.y_size,
            mines=self._opts.mines,
            per_cell=self._opts.per_cell,
            lives=self._opts.lives,
            first_success=self._opts.first_success,
        )
        self._send_reset_update()

    def restart_game(self) -> None:
        """See AbstractController."""
        if not self._game.mf:
            return
        super().restart_game()
        self._game = game.Game(minefield=self._game.mf, lives=self._opts.lives)
        self._send_reset_update()

    def select_cell(self, coord: Coord_T) -> None:
        """See AbstractController."""
        super().select_cell(coord)
        cells = self._game.select_cell(coord)
        self._send_updates(cells)

    def flag_cell(self, coord: Coord_T, *, flag_only: bool = False) -> None:
        """See AbstractController."""
        super().flag_cell(coord)

        cell_state = self._game.board[coord]
        if cell_state is CellUnclicked():
            self._game.set_cell_flags(coord, 1)
        elif isinstance(cell_state, CellFlag):
            if cell_state.num == self._opts.per_cell:
                if flag_only:
                    return
                self._game.set_cell_flags(coord, 0)
            else:
                self._game.set_cell_flags(coord, cell_state.num + 1)

        self._send_updates({coord: self._game.board[coord]})

    def remove_cell_flags(self, coord: Coord_T) -> None:
        """See AbstractController."""
        super().remove_cell_flags(coord)
        self._game.set_cell_flags(coord, 0)
        self._send_updates({coord: self._game.board[coord]})

    def chord_on_cell(self, coord: Coord_T) -> None:
        """See AbstractController."""
        super().chord_on_cell(coord)
        cells = self._game.chord_on_cell(coord)
        self._send_updates(cells)

    def resize_board(self, x_size: int, y_size: int, mines: int) -> None:
        """See AbstractController."""
        super().resize_board(x_size=x_size, y_size=y_size, mines=mines)
        if (
            x_size == self._opts.x_size
            and y_size == self._opts.y_size
            and mines == self._opts.mines
        ):
            logger.info(
                "No resize required as the parameters are unchanged, starting a new game"
            )
            self.new_game()
            return

        logger.info(
            "Resizing board from %sx%s with %s mines to %sx%s with %s mines",
            self._opts.x_size,
            self._opts.y_size,
            self._opts.mines,
            x_size,
            y_size,
            mines,
        )
        self._opts.x_size = x_size
        self._opts.y_size = y_size
        self._opts.mines = mines

        self._game = game.Game(
            x_size=self._opts.x_size,
            y_size=self._opts.y_size,
            mines=self._opts.mines,
            per_cell=self._opts.per_cell,
            lives=self._opts.lives,
            first_success=self._opts.first_success,
        )
        self._send_resize_update()

    def set_first_success(self, value: bool) -> None:
        """
        Set whether the first click should be a guaranteed success.
        """
        super().set_first_success(value)
        self._opts.first_success = value

    def set_per_cell(self, value: int) -> None:
        """
        Set the maximum number of mines per cell.
        """
        super().set_per_cell(value)
        if self._opts.per_cell != value:
            self._opts.per_cell = value
            if self._game.state.unstarted():
                self.new_game()

    # --------------------------------------------------------------------------
    # Helper methods
    # --------------------------------------------------------------------------
    def _send_reset_update(self) -> None:
        self._send_updates({})
        self._notif.reset()
        self._last_update = _SharedInfo()

    def _send_resize_update(self) -> None:
        self._send_updates({})
        self._notif.resize_minefield(self._opts.x_size, self._opts.y_size)
        self._notif.set_mines(self._opts.mines)
        self._notif.reset()

    def _send_updates(self, cells_updated: Dict[Coord_T, CellContentsType]) -> None:
        """Send updates to registered listeners."""
        end_game_info = None
        if (
            self._game.is_finished()
            and self._game.state is not self._last_update.game_state
        ):
            end_game_info = api.EndedGameInfo(
                game_state=self._game.state,
                difficulty=self._game.difficulty,
                per_cell=self._game.per_cell,
                start_time=self._game.start_time,
                elapsed=self._game.get_elapsed(),
                bbbv=self._game.mf.bbbv,
                flagging=self._game.get_flag_proportion(),
                minefield_known=self._game.minefield_known,
            )
        update = _SharedInfo(
            cell_updates=cells_updated,
            mines_remaining=self._game.mines_remaining,
            lives_remaining=self._game.lives_remaining,
            game_state=self._game.state,
            end_game_info=end_game_info,
        )

        # Send updates to registered frontends.
        if update.cell_updates:
            self._notif.update_cells(update.cell_updates)
        if update.mines_remaining != self._last_update.mines_remaining:
            self._notif.update_mines_remaining(update.mines_remaining)
        # if update.lives_remaining != self._last_update.lives_remaining:
        #     self._notif.update_lives_remaining(update.lives_remaining)
        if update.game_state is not self._last_update.game_state:
            self._notif.update_game_state(update.game_state)
        if update.end_game_info is not None:
            self._notif.handle_finished_game(update.end_game_info)

        self._last_update = update


class CreateController(api.AbstractController):
    """A controller for creating boards."""

    def __init__(
        self, opts: utils.GameOptsStruct, *, notif: Optional[api.Caller] = None
    ):
        super().__init__(opts, notif=notif)
        self._board: brd.Board = brd.Board(self._opts.x_size, self._opts.y_size)
        self._flags: int = 0
        self._notif.set_mines(self._flags)
        self._notif.reset()

    @property
    def board(self) -> brd.Board:
        return self._board

    def new_game(self) -> None:
        """See AbstractController."""
        super().new_game()
        self._board = brd.Board(self._opts.x_size, self._opts.y_size)
        self._flags = 0
        self._notif.reset()

    def restart_game(self) -> None:
        super().restart_game()
        self.new_game()

    def select_cell(self, coord: Coord_T) -> None:
        super().select_cell(coord)
        cell = self._board[coord]
        if cell is CellUnclicked():
            self._board[coord] = CellNum(0)
        elif isinstance(cell, CellNum):
            self._board[coord] += 1
        else:
            return
        self._notif.update_cells({coord: self._board[coord]})

    def flag_cell(self, coord: Coord_T, *, flag_only: bool = False) -> None:
        super().flag_cell(coord)
        cell = self._board[coord]

        if cell is CellUnclicked():
            self._board[coord] = CellMine(1)
            self._flags += 1
        elif isinstance(cell, CellMine):
            if cell.num == self._opts.per_cell:
                if flag_only:
                    return
                self._board[coord] = CellUnclicked()
                self._flags -= self._opts.per_cell
            else:
                self._board[coord] += 1
                self._flags += 1
        elif isinstance(cell, CellNum):
            self.board[coord] = CellUnclicked()
        else:
            return
        self._notif.update_cells({coord: self._board[coord]})
        self._notif.update_mines_remaining(self._flags)

    def chord_on_cell(self, coord: Coord_T) -> None:
        super().chord_on_cell(coord)

    def remove_cell_flags(self, coord: Coord_T) -> None:
        super().remove_cell_flags(coord)
        cell = self._board[coord]
        if not isinstance(cell, CellMine):
            return
        self._board[coord] = CellUnclicked()
        self._flags -= cell.num
        self._notif.update_cells({coord: self._board[coord]})
        self._notif.update_mines_remaining(self._flags)

    def resize_board(self, x_size: int, y_size: int, mines: int) -> None:
        super().resize_board(x_size=x_size, y_size=y_size, mines=mines)
        if x_size == self._opts.x_size and y_size == self._opts.y_size:
            logger.info(
                "No resize required as the parameters are unchanged, starting a new game"
            )
            self.new_game()
            return

        logger.info(
            "Resizing board from %sx%s to %sx%s",
            self._opts.x_size,
            self._opts.y_size,
            x_size,
            y_size,
        )
        self._opts.x_size = x_size
        self._opts.y_size = y_size
        self._notif.resize_minefield(x_size, y_size)
        self.new_game()

    def set_first_success(self, value: bool) -> None:
        super().set_first_success(value)
        # Store the value so it can be retrieved from the next controller.
        self._opts.first_success = value

    def set_per_cell(self, value: int) -> None:
        super().set_per_cell(value)
        self._opts.per_cell = value