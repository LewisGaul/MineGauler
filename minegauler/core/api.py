"""
api.py - API on to the core, providing all information needed by frontends

September 2019, Lewis Gaul

Exports:
TODO
"""

__all__ = (
    "AbstractController",
    "AbstractListener",
    "AbstractSwitchingController",
    "Caller",
    "EndedGameInfo",
)

import abc
import logging
import os
from typing import Callable, Dict, Iterable, List, Optional, Union

import attr

from ..core import board as brd
from ..shared import utils
from ..types import CellContents, GameState, UIMode
from ..typing import Coord_T


@attr.attrs(auto_attribs=True)
class GameInfo:
    """General information about a game."""

    @attr.attrs(auto_attribs=True)
    class FinishedInfo:
        start_time: float
        elapsed: float
        bbbv: int
        rem_bbbv: int
        bbbvps: float
        prop_complete: float
        prop_flagging: float

    game_state: GameState
    x_size: int
    y_size: int
    mines: int
    per_cell: int
    finished_info: Optional[FinishedInfo] = None


@attr.attrs(auto_attribs=True)
class EndedGameInfo:
    """Information about a finished game."""

    game_state: GameState
    difficulty: str
    per_cell: int
    start_time: float
    elapsed: float
    bbbv: int
    flagging: float
    minefield_known: bool


class AbstractListener(metaclass=abc.ABCMeta):
    """
    An abstract class outlining methods that should be implemented to receive
    updates on changes to state. Instances of a concrete implementation can
    then be registered to listen for callbacks.
    """

    @abc.abstractmethod
    def reset(self) -> None:
        """
        Called to indicate the state should be reset.
        """
        return NotImplemented

    @abc.abstractmethod
    def resize_minefield(self, x_size: int, y_size: int) -> None:
        """
        Called to indicate the board is being changed.

        :param x_size:
            The number of columns.
        :param y_size:
            The number of rows.
        """
        return NotImplemented

    @abc.abstractmethod
    def set_mines(self, mines: int) -> None:
        """
        Called to indicate the number of mines at reset has changed.
        """
        return NotImplemented

    @abc.abstractmethod
    def update_cells(self, cell_updates: Dict[Coord_T, CellContents]) -> None:
        """
        Called when one or more cells were updated.

        :param cell_updates:
            Mapping of coordinates that were changed to the new cell state.
        """
        return NotImplemented

    @abc.abstractmethod
    def update_game_state(self, game_state: GameState) -> None:
        """
        Called when the game state changes.

        :param game_state:
            The new game state.
        """
        return NotImplemented

    @abc.abstractmethod
    def update_mines_remaining(self, mines_remaining: int) -> None:
        """
        Called when the number of mines remaining changes.

        :param mines_remaining:
            The new number of mines remaining.
        """
        return NotImplemented

    @abc.abstractmethod
    def handle_finished_game(self, info: EndedGameInfo) -> None:
        """
        Called once when a game ends.

        :param info:
            A store of end-game information.
        """
        return NotImplemented

    @abc.abstractmethod
    def switch_mode(self, mode: UIMode) -> None:
        """
        Called to indicate the game mode has change.

        :param mode:
            The mode to change to.
        """
        return NotImplemented

    @abc.abstractmethod
    def handle_exception(self, method: str, exc: Exception) -> None:
        """
        Called if an exception occurs when calling any of the other methods on
        the class, to allow the implementer of the class to handle (e.g. log)
        any errors.

        :param method:
            The method that the exception occurred in.
        :param exc:
            The caught exception.
        """
        return NotImplemented


class Caller(AbstractListener):
    """
    Pass on calls to registered listeners.
    """

    _count: int = 0

    def __init__(self, listeners: Iterable[AbstractListener] = None):
        """
        Create the implementation for all

        :param listeners:
        """
        self._listeners: List[AbstractListener] = list(listeners) if listeners else []
        self._id: int = self._count
        self._logger = logging.getLogger(f"{__name__}.{type(self).__name__}{self._id}")

        self.__class__._count += 1

        # Do the method wrapping here because we need the registered listeners.
        for method in AbstractListener.__abstractmethods__:
            setattr(self, method, self._call_registered(method))

    def register_listener(self, listener: AbstractListener) -> None:
        """
        Register a listener to receive updates from the controller.

        :param listener:
            An AbstractListener instance to register.
        """
        self._listeners.append(listener)

    def unregister_listener(self, listener: AbstractListener) -> None:
        """
        Unregister a listener to receive updates from the controller.

        Does nothing if not registered.

        :param listener:
            An AbstractListener instance to unregister.
        """
        try:
            self._listeners.remove(listener)
        except ValueError:
            self._logger.debug("Listener not registered - nothing to do")

    def _call_registered(self, func: str) -> Callable:
        """
        Decorator to call all registered listeners.

        :param func:
            The name of the method to decorate.
        :return:
            The decorated version of the method.
        """
        if not hasattr(self, func + "_orig"):
            setattr(self, func + "_orig", getattr(self, func))

        def wrapped(*args, **kwargs):
            getattr(self, func + "_orig")(*args, **kwargs)
            for listener in self._listeners:
                try:
                    getattr(listener, func)(*args, **kwargs)
                except Exception as e:
                    self._logger.warning(
                        f"Error ocurred calling {func}() on {listener}"
                    )
                    listener.handle_exception(func, e)

        return wrapped

    def reset(self) -> None:
        """
        Called to indicate the state should be reset.
        """
        self._logger.debug("Calling reset()")

    def resize_minefield(self, x_size: int, y_size: int) -> None:
        """
        Called to indicate the board shape has changed.

        :param x_size:
            The number of rows.
        :param y_size:
            The number of columns.
        """
        self._logger.debug(f"Calling resize_minefield() with {x_size}, {y_size}")

    def set_mines(self, mines: int) -> None:
        """
        Called to indicate the number of mines at reset has changed.
        """
        self._logger.debug(f"Calling set_mines() with {mines}")

    def update_cells(self, cell_updates: Dict[Coord_T, CellContents]) -> None:
        """
        Called when one or more cells were updated.

        :param cell_updates:
            Mapping of coordinates that were changed to the new cell state.
        """
        self._logger.debug(
            f"Calling update_cells() with {len(cell_updates)} updated cells"
        )

    def update_game_state(self, game_state: GameState) -> None:
        """
        Called when the game state changes.

        :param game_state:
            The new game state.
        """
        self._logger.debug(f"Calling update_game_state() with {game_state}")

    def update_mines_remaining(self, mines_remaining: int) -> None:
        """
        Called when the number of mines remaining changes.

        :param mines_remaining:
            The new number of mines remaining.
        """
        self._logger.debug(f"Calling update_mines_remaining() with {mines_remaining}")

    def handle_finished_game(self, info: EndedGameInfo) -> None:
        """
        Called once when a game ends.

        :param info:
            A store of end-game information.
        """
        self._logger.debug(f"Calling handle_finished_game() with {info}")

    def switch_mode(self, mode: UIMode) -> None:
        """
        Called to indicate the game mode has change.

        :param mode:
            The mode to change to.
        """
        self._logger.debug(f"Calling switch_mode() with {mode}")

    def handle_exception(self, method: str, exc: Exception) -> None:
        """
        Not used in this class - provided only to satisfy the ABC.
        """
        return NotImplemented


class AbstractController(metaclass=abc.ABCMeta):
    """
    Abstract controller base class. Listeners can be registered for receiving
    updates.
    """

    def __init__(self, opts: utils.GameOptsStruct, *, notif: Optional[Caller] = None):
        self._opts = utils.GameOptsStruct.from_structs(opts)
        # The registered functions to be called with updates.
        self._notif: Caller = notif if notif else Caller()
        self._logger = logging.getLogger(
            ".".join([type(self).__module__, type(self).__name__])
        )

    def register_listener(self, listener: AbstractListener) -> None:
        """
        Register a listener to receive updates from the controller.

        :param listener:
            An AbstractListener instance to register.
        """
        self._logger.info(
            "Registering listener: %s.%s",
            type(listener).__module__,
            type(listener).__name__,
        )
        self._notif.register_listener(listener)
        # TODO Implement in subclass to update with current state.

    def unregister_listener(self, listener: AbstractListener) -> None:
        """
        Unregister a listener to receive updates from the controller.

        Does nothing if not registered.

        :param listener:
            An AbstractListener instance to unregister.
        """
        self._logger.info(
            "Unregistering listener: %s.%s",
            type(listener).__module__,
            type(listener).__name__,
        )
        self._notif.unregister_listener(listener)

    @property
    @abc.abstractmethod
    def board(self) -> brd.Board:
        return NotImplemented

    @abc.abstractmethod
    def get_game_info(self) -> GameInfo:
        """Get information about the current game."""
        return NotImplemented

    def get_game_options(self) -> utils.GameOptsStruct:
        return self._opts

    # --------------------------------------------------------------------------
    # Methods triggered by user interaction
    # --------------------------------------------------------------------------
    @abc.abstractmethod
    def new_game(self) -> None:
        """
        Create a new game, refresh the board state.
        """
        self._logger.info("New game requested, refreshing the board")

    @abc.abstractmethod
    def restart_game(self) -> None:
        """
        Restart the current game, refresh the board state.
        """
        self._logger.info("Restart game requested, refreshing the board")

    @abc.abstractmethod
    def select_cell(self, coord: Coord_T) -> None:
        """
        Select a cell for a regular click.
        """
        self._logger.debug("Cell %s selected", coord)

    @abc.abstractmethod
    def flag_cell(self, coord: Coord_T, *, flag_only: bool = False) -> None:
        """
        Select a cell for flagging.
        """
        self._logger.debug("Cell %s selected for flagging", coord)

    @abc.abstractmethod
    def chord_on_cell(self, coord: Coord_T) -> None:
        """
        Select a cell for chording.
        """
        self._logger.debug("Cell %s selected for chording", coord)

    @abc.abstractmethod
    def remove_cell_flags(self, coord: Coord_T) -> None:
        """
        Remove flags in a cell, if any.
        """
        self._logger.debug("Flags in cell %s being removed", coord)

    @abc.abstractmethod
    def resize_board(self, x_size: int, y_size: int, mines: int) -> None:
        """
        Resize the board and/or change the number of mines.
        """
        self._logger.info(
            "Resizing the board to %sx%s with %s mines", x_size, y_size, mines
        )

    @abc.abstractmethod
    def set_first_success(self, value: bool) -> None:
        """
        Set whether the first click should be a guaranteed success.
        """
        self._logger.debug("Setting first success to %s", value)

    @abc.abstractmethod
    def set_per_cell(self, value: int) -> None:
        """
        Set the maximum number of mines per cell.
        """
        self._logger.debug("Setting per cell to %s", value)

    @abc.abstractmethod
    def save_current_minefield(self, file: os.PathLike) -> None:
        """
        Save the current minefield to file.

        :param file:
            The location of the file to save to. Should have the extension
            ".mgb".
        """
        self._logger.debug("Saving current minefield to file: %s", file)

    @abc.abstractmethod
    def load_minefield(self, mf_or_file: Union[os.PathLike, brd.Minefield]) -> None:
        """
        Load a minefield, either from file or directly.

        :param mf_or_file:
            Either the location of the file to load from (with extension ".mgb")
            or the minefield to load.
        """
        self._logger.debug("Loading minefield: %s", mf_or_file)


class AbstractSwitchingController(AbstractController):
    """An abstract base class for controllers that support switching mode."""

    @abc.abstractmethod
    def switch_mode(self, mode: UIMode) -> None:
        """
        Switch the mode of the UI, e.g. into 'create' mode.
        """
        self._logger.info("Requested switch to mode %s", mode)
