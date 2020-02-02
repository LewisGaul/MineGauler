"""
engine.py - The core game logic

November 2018, Lewis Gaul

Exports:
BaseController (class)
    Implementation of game logic and provision of functions to be called by a
    frontend implementation.
"""

__all__ = ("BaseController", "CreateController", "GameController")

import json
import logging
import os
from typing import Dict, Optional, Union

import attr

from ..shared import utils
from ..types import CellContents, GameState, UIMode
from ..typing import Coord_T
from . import api
from . import board as brd
from . import game


logger = logging.getLogger(__name__)


def _save_minefield(mf: brd.Minefield, file: os.PathLike) -> None:
    """
    Save a minefield to file.

    :param mf:
        The minefield to save.
    """
    if os.path.isfile(file):
        logger.warning("Overwriting file at %s", file)
    elif os.path.isdir(file):
        logger.error("Unable to save minefield - directory exists at %s", file)
        return
    with open(file, "w") as f:
        json.dump(mf.to_json(), f)


@attr.attrs(auto_attribs=True)
class _SharedInfo:
    """
    Information to pass to frontends.
    
    Elements:
    cell_updates ({(int, int): CellContents, ...})
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

    cell_updates: Dict[Coord_T, CellContents] = attr.Factory(dict)
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
        self._mode = UIMode.GAME
        self._active_ctrlr: api.AbstractController = GameController(
            self._opts, notif=self._notif
        )

    def reinitialise(self):
        """Reinitialise the concrete game controller."""
        self._mode = UIMode.GAME
        self._active_ctrlr: api.AbstractController = GameController(
            self._opts, notif=self._notif
        )

    def switch_mode(self, mode: UIMode, *args, **kwargs) -> None:
        """Switch the mode of the UI, e.g. into 'create' mode."""
        super().switch_mode(mode)
        if mode is self._mode:
            logger.debug("Ignore switch mode request because mode is already %s", mode)
            return
        if mode is UIMode.GAME:
            self._active_ctrlr = GameController(
                self._opts, notif=self._notif, *args, **kwargs
            )
        elif mode is UIMode.CREATE:
            self._active_ctrlr = CreateController(
                self._opts, notif=self._notif, *args, **kwargs
            )
        else:
            raise ValueError(f"Unrecognised UI mode: {mode}")
        self._mode = mode

    # ----------------------------------
    # Delegated abstractmethods
    # ----------------------------------
    @property
    def board(self) -> brd.Board:
        return self._active_ctrlr.board

    def get_game_info(self) -> api.GameInfo:
        return self._active_ctrlr.get_game_info()

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

    def save_current_minefield(self, file: os.PathLike) -> None:
        self._active_ctrlr.save_current_minefield(file)

    def load_minefield(self, mf_or_file: Union[os.PathLike, brd.Minefield]) -> None:
        if isinstance(mf_or_file, brd.Minefield):
            mf = mf_or_file
        else:
            with open(mf_or_file) as f:
                mf = brd.Minefield.from_json(json.load(f))
        self._opts.x_size = mf.x_size
        self._opts.y_size = mf.y_size
        self._opts.mines = mf.nr_mines

        if self._mode is UIMode.CREATE:
            self.switch_mode(UIMode.GAME, minefield=mf)
            self._notif.switch_mode(UIMode.GAME)
        else:
            self._active_ctrlr.load_minefield(mf)


class GameController(api.AbstractController):
    """
    Class for processing all game logic. Implements functions defined in
    AbstractController that are called from UI.
    
    Attributes:
    opts (GameOptsStruct)
        Options for use in games.
    """

    def __init__(
        self,
        opts: utils.GameOptsStruct,
        *,
        notif: Optional[api.Caller] = None,
        minefield: Optional[Union[os.PathLike, brd.Minefield]] = None,
    ):
        """
        :param opts:
            Game options.
        :param notif:
            Optionally provide a notifier defining callbacks.
        :param minefield:
            Optionally provide minefield to create the initial game from.
        """
        super().__init__(opts, notif=notif)

        self._drag_select = False
        self._name = ""
        self._game: game.Game = None  # Populated in new_game()
        self._last_update: _SharedInfo = _SharedInfo()
        self._notif.update_game_state(GameState.READY)
        self._notif.set_mines(self._opts.mines)
        if minefield:
            self.load_minefield(minefield)
        else:
            self.new_game()

    @property
    def board(self) -> brd.Board:
        return self._game.board

    def get_game_info(self) -> api.GameInfo:
        ret = api.GameInfo(
            game_state=self._game.state,
            x_size=self._game.x_size,
            y_size=self._game.y_size,
            mines=self._game.mines,
            per_cell=self._game.per_cell,
        )
        if self._game.state.finished():
            ret.finished_info = api.GameInfo.FinishedInfo(
                start_time=self._game.start_time,
                elapsed=self._game.get_elapsed(),
                bbbv=self._game.mf.bbbv,
                rem_bbbv=self._game.get_rem_3bv(),
                bbbvps=self._game.get_3bvps(),
                prop_complete=self._game.get_prop_complete(),
                prop_flagging=self._game.get_flag_proportion(),
            )
        return ret

    # --------------------------------------------------------------------------
    # Methods triggered by user interaction
    # --------------------------------------------------------------------------
    def new_game(self) -> None:
        """See AbstractController."""
        super().new_game()
        if self._opts.mines > self._opts.per_cell * (
            self._opts.x_size * self._opts.y_size - 1
        ):
            logger.debug(
                "Reducing number of mines from %d to %d because they don't fit",
                self._opts.mines,
                self._opts.x_size * self._opts.y_size - 1,
            )
            self._opts.mines = self._opts.x_size * self._opts.y_size - 1
            self._notif.set_mines(self._opts.mines)
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
        if cell_state is CellContents.Unclicked:
            self._game.set_cell_flags(coord, 1)
        elif isinstance(cell_state, CellContents.Flag):
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
        if not self._game.state.started():
            self._game.first_success = value

    def set_per_cell(self, value: int) -> None:
        """
        Set the maximum number of mines per cell.
        """
        super().set_per_cell(value)
        if self._opts.per_cell != value:
            self._opts.per_cell = value
            if not (self._game.state.started() or self._game.minefield_known):
                self.new_game()

    def save_current_minefield(self, file: os.PathLike) -> None:
        """
        Save the current minefield to file.

        :param file:
            The location of the file to save to. Should have the extension
            ".mgb".
        """
        super().save_current_minefield(file)
        if self._game.mf is None:
            logger.warning("Unable to save current minefield - doesn't exist")
            return
        _save_minefield(self._game.mf, file)

    def load_minefield(self, mf_or_file: Union[os.PathLike, brd.Minefield]) -> None:
        """
        Load a minefield, either from file or directly.

        :param mf_or_file:
            Either the location of the file to load from (with extension ".mgb")
            or the minefield to load.
        """
        if isinstance(mf_or_file, brd.Minefield):
            mf = mf_or_file
        else:
            with open(mf_or_file) as f:
                mf = brd.Minefield.from_json(json.load(f))

        self._opts.x_size = mf.x_size
        self._opts.y_size = mf.y_size
        self._opts.mines = mf.nr_mines
        self._game = game.Game(minefield=mf, lives=self._opts.lives)
        self._send_resize_update()

    # --------------------------------------------------------------------------
    # Helper methods
    # --------------------------------------------------------------------------
    def _send_reset_update(self) -> None:
        self._send_updates(dict())
        self._notif.reset()
        self._last_update = _SharedInfo()

    def _send_resize_update(self) -> None:
        self._send_updates(dict())
        self._notif.resize_minefield(self._opts.x_size, self._opts.y_size)
        self._notif.set_mines(self._opts.mines)
        self._notif.reset()

    def _send_updates(self, cells_updated: Dict[Coord_T, CellContents]) -> None:
        """Send updates to registered listeners."""
        end_game_info = None
        if (
            self._game.state.finished()
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
        self._notif.update_game_state(GameState.READY)
        self._notif.set_mines(self._flags)
        self._notif.reset()

    @property
    def board(self) -> brd.Board:
        return self._board

    def get_game_info(self) -> api.GameInfo:
        return api.GameInfo(
            game_state=GameState.ACTIVE,
            x_size=self._opts.x_size,
            y_size=self._opts.y_size,
            mines=self._flags,
            per_cell=self._opts.per_cell,
        )

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
        if cell is CellContents.Unclicked:
            self._board[coord] = CellContents.Num(0)
        elif isinstance(cell, CellContents.Num):
            self._board[coord] += 1
        else:
            return
        self._notif.update_cells({coord: self._board[coord]})

    def flag_cell(self, coord: Coord_T, *, flag_only: bool = False) -> None:
        super().flag_cell(coord)
        cell = self._board[coord]

        if cell is CellContents.Unclicked:
            self._board[coord] = CellContents.Mine(1)
            self._flags += 1
        elif isinstance(cell, CellContents.Mine):
            if cell.num == self._opts.per_cell:
                if flag_only:
                    return
                self._board[coord] = CellContents.Unclicked
                self._flags -= self._opts.per_cell
            else:
                self._board[coord] += 1
                self._flags += 1
        elif isinstance(cell, CellContents.Num):
            self.board[coord] = CellContents.Unclicked
        else:
            return
        self._notif.update_cells({coord: self._board[coord]})
        self._notif.update_mines_remaining(self._flags)

    def chord_on_cell(self, coord: Coord_T) -> None:
        super().chord_on_cell(coord)

    def remove_cell_flags(self, coord: Coord_T) -> None:
        super().remove_cell_flags(coord)
        cell = self._board[coord]
        if not isinstance(cell, CellContents.Mine):
            return
        self._board[coord] = CellContents.Unclicked
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

    def save_current_minefield(self, file: os.PathLike) -> None:
        """
        Save the current created minefield to file.

        :param file:
            The location of the file to save to. Should have the extension
            ".mgb".
        """
        super().save_current_minefield(file)
        mines_grid = utils.Grid(self._opts.x_size, self._opts.y_size)
        for c in self._board.all_coords:
            if type(self._board[c]) is CellContents.Mine:
                mines_grid[c] = self._board[c].num
        mf = brd.Minefield.from_grid(mines_grid, per_cell=self._opts.per_cell)
        _save_minefield(mf, file)

    def load_minefield(self, mf_or_file: Union[os.PathLike, brd.Minefield]) -> None:
        return NotImplemented
