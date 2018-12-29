"""
game_engine.py - The core game logic

November 2018, Lewis Gaul

Exports:
AbstractController (class)
    Outline of functions available to be called by a frontend.
Controller (class)
    Implementation of game logic and provision of functions to be called by a
    frontend implementation.
"""

import functools
import logging
import time as tm
from abc import ABC, abstractmethod

from minegauler.backend.minefield import Minefield
from minegauler.backend.utils import Board
from minegauler.shared.internal_types import *
from minegauler.shared.utils import get_num_pos_args_accepted, AbstractStruct


logger = logging.getLogger(__name__)



def _ignore_if(*, game_state=None, cell_state=None):
    """
    Return a decorator which prevents a method from running if any of the given
    parameters are satisfied.
    
    Arguments:
    game_state=None (GameState | (GameState, ...) | None)
        A game state or iterable of game states to match against.
    cell_state=None (subclass of CellContentsType | (..., ...) | None)
        A cell contents type or iterable of the same to match against. The
        decorated method must take the cell coordinate as the first argument.
    """
    def decorator(method):
        if cell_state is None:
            @functools.wraps(method)
            def wrapped(self, *args, **kwargs):
                if (game_state is not None and
                    (self.game_state == game_state or
                     self.game_state in game_state)):
                    return
                return method(self, *args, **kwargs)
        else:
            @functools.wraps(method)
            def wrapped(self, coord, *args, **kwargs):
                if ((game_state is not None and
                     (self.game_state == game_state or
                      self.game_state in game_state)) or
                    isinstance(self.board[coord], cell_state)):
                    return
                return method(self, coord, *args, **kwargs)
        
        return wrapped
    return decorator


def _ignore_if_not(*, game_state=None, cell_state=None):
    """
    Return a decorator which prevents a method from running if any of the given
    parameters are satisfied.
    
    Arguments:
    game_state=None (GameState | (GameState, ...) | None)
        A game state or iterable of game states to match against.
    cell_state=None (subclass of CellContentsType | (..., ...) | None)
        A cell contents type or iterable of the same to match against. The
        decorated method must take the cell coordinate as the first argument.
    """
    def decorator(method):
        if cell_state is None:
            @functools.wraps(method)
            def wrapped(self, *args, **kwargs):
                if (game_state is not None and
                    self.game_state != game_state and
                    self.game_state not in game_state):
                    return
                return method(self, *args, **kwargs)
        else:
            @functools.wraps(method)
            def wrapped(self, coord, *args, **kwargs):
                if ((game_state is not None and
                     self.game_state != game_state and
                     self.game_state not in game_state) or
                    not isinstance(self.board[coord], cell_state)):
                    return
                return method(self, coord, *args, **kwargs)
        
        return wrapped
    return decorator
    

class GameOptsStruct(AbstractStruct):
    """
    Structure of game options.
    """
    _elements = {
        'x_size':        8,
        'y_size':        8,
        'mines':         10,
        'first_success': True,
        'per_cell':      1,
        'lives':         1,
        'game_mode':     GameFlagMode.NORMAL,
    }


class SharedInfo:
    """
    Information to pass to front-ends.
    
    Attributes:
    cell_updates ({(int, int): CellContentsType, ...})
        Dictionary of updates to cells, mapping the coordinate to the new
        contents of the cell.
    game_state (GameState)
        The state of the game.
    mines_remaining (int)
        The number of mines remaining to be found, given by
        [total mines] - [number of flags]. Can be negative if there are too many
        flags.
    elapsed_time (float | None)
        The time elapsed if the game has ended, otherwise None.
    """
    cell_updates    = {}
    game_state      = GameState.INVALID
    mines_remaining = 0
    elapsed_time    = None



class AbstractController(ABC):
    """
    Abstract controller base class. Callbacks can be registered for receiving
    updates.
    """

    def __init__(self):
        # The registered functions to be called with updates.
        self._registered_callbacks = []

    def register_callback(self, callback):
        """
        Register a callback function to receive updates from a game controller.
        If the callback is invalid it will not be registered and an error will
        be logged.
        
        Arguments:
        callback (callable, taking one argument)
            The callback function/method, to be called with the update 
            information (of type SharedInfo).
        """

        # Perform some validation on the provided callback.
        try:
            min_args, max_args = get_num_pos_args_accepted(callback)
        except ValueError as e:
            logger.warning("Unable to check callback function")
            logger.debug("%s", e)
        except TypeError:
            logger.error("Invalid callback function - does not appear to be "
                         "callable: %s",
                         callback)
            return
        else:
            if min_args > 1 or max_args < 1:
                logger.error("Invalid callback function - must be able to "
                             "accept one argument: %s",
                             callback)
                return

        logger.info("%s: Registering callback: %s", type(self), callback)
        self._registered_callbacks.append(callback)

    @abstractmethod
    def _send_callback_updates(self):
        """
        Send updates using the registered callbacks.
        """
        logger.info("%s: Sending updates using registered callbacks",
                    type(self))

    # --------------------------------------------------------------------------
    # Methods triggered by user interaction
    # --------------------------------------------------------------------------
    @abstractmethod
    def new_game(self):
        """
        Create a new game, refresh the board state.
        """
        logger.info("%s: New game requested, refreshing the board", type(self))

    @abstractmethod
    def restart_game(self):
        """
        Restart the current game, refresh the board state.
        """
        logger.info("%s: Restart game requested, refreshing the board",
                    type(self))

    @abstractmethod
    def select_cell(self, coord):
        """
        Select a cell for a regular click.
        """
        logger.info("%s: Cell %s selected", type(self), coord)

    @abstractmethod
    def flag_cell(self, coord):
        """
        Select a cell for flagging.
        """
        logger.info("%s: Cell %s selected for flagging", type(self), coord)

    @abstractmethod
    def chord_on_cell(self, coord):
        """
        Select a cell for chording.
        """
        logger.info("%s: Cell %s selected for chording", type(self), coord)

    @abstractmethod
    def remove_cell_flags(self, coord):
        """
        Remove flags in a cell, if any.
        """
        logger.info("%s: Flags in cell %s being removed", type(self), coord)

    # @abstractmethod
    # def change_settings(self, **kwargs):
    #     """
    #     Update the settings to be used for future games.
    #     """
    #     logger.info("%s: Changing settings", type(self)) #@@@

    @abstractmethod
    def resize_board(self, x_size, y_size, mines):
        """
        Resize the board and/or change the number of mines.
        """
        logger.info("%s: Resizing the board to %sx%s with %s mines",
                    type(self), x_size, y_size, mines)



class Controller(AbstractController):
    """
    Class for processing all game logic. Implements functions defined in
    AbstractController that are called from UI.
    
    Attributes:
    opts (GameOptsStruct)
        Options for use in games.
    """

    def __init__(self, opts):
        """
        Arguments:
        opts (GameOptsStruct)
            Object containing the required game options as attributes.
        """

        super().__init__()

        for kw in GameOptsStruct._elements:
            if not hasattr(opts, kw):
                raise ValueError(f"Missing option {kw}")
                
        self.opts = GameOptsStruct._from_struct(opts)
        # Only normal game mode currently supported.
        self.opts.game_mode = GameFlagMode.NORMAL
        # Initialise game board.
        self.board = Board(opts.x_size, opts.y_size)
        # Keep track of changes made to cell states to be passed to UI.
        self._cell_updates = {}
        # Game-specific data.
        self.game_state = GameState.INVALID
        self.mines_remaining = 0
        self.lives_remaining = 0
        self.start_time = None
        self.end_time = None
        self.mf = Minefield(self.opts.x_size, self.opts.y_size, self.opts.mines,
                            self.opts.per_cell, create=False)
        self._init_game()
    
    # --------------------------------------------------------------------------
    # Methods triggered by user interaction
    # --------------------------------------------------------------------------
    def new_game(self):
        """See AbstractController."""
        
        super().new_game()
        
        self.mf = Minefield(self.opts.x_size, self.opts.y_size, self.opts.mines,
                            self.opts.per_cell, create=False)
        self._init_game()
        for c in self.board.all_coords:
            self._set_cell(c, CellUnclicked())
            
        self._send_callback_updates()
    
    @_ignore_if(game_state='INVALID')
    def restart_game(self):
        """See AbstractController."""
        
        super().restart_game()
        
        self._init_game()
        for c in self.board.all_coords:
            self._set_cell(c, CellUnclicked())
            
        self._send_callback_updates()
    
    @_ignore_if_not(game_state=('READY', 'ACTIVE'), cell_state=CellUnclicked)
    def select_cell(self, coord):
        """See AbstractController."""
        
        super().select_cell(coord)
            
        # Check if first click.
        if self.game_state == GameState.READY:
            if not self.mf.is_created:
                # Create the minefield.
                if self.opts.first_success:
                    safe_coords = self.mf.get_nbrs(coord, include_origin=True)
                    logger.debug(
                        "Trying to create minefield with the following safe "
                        "coordinates: %s", safe_coords)
                    try:
                        self.mf.create(safe_coords)
                    except ValueError:
                        logger.info(
                            "Unable to give opening on the first click, "
                            "still ensuring a safe click")
                        self.mf.create(safe_coords=[coord])
                    else:
                        logger.debug("Success")
                else:
                    self.mf.create()
                    logger.debug(
                        "Creating minefield with first success turned off")
            self.game_state = GameState.ACTIVE
            self.start_time = tm.time()
            
        self._select_cell_action(coord)
        
        if self.game_state != GameState.LOST:
            self._check_for_completion()
        
        self._send_callback_updates()

    @_ignore_if_not(game_state=('READY', 'ACTIVE'),
                    cell_state=(CellFlag, CellUnclicked))
    def flag_cell(self, coord):
        """See AbstractController."""
        
        super().flag_cell(coord)
        
        if self.opts.game_mode == GameFlagMode.NORMAL:
            if self.board[coord] == CellUnclicked():
                self._set_cell(coord, CellFlag(1))
                self.mines_remaining -= 1
            elif type(self.board[coord]) is CellFlag:
                if self.board[coord] == CellFlag(self.opts.per_cell):
                    self._set_cell(coord, CellUnclicked())
                    self.mines_remaining += self.opts.per_cell
                else:
                    self._set_cell(coord, self.board[coord] + 1)
                    self.mines_remaining -= 1
        
        self._send_callback_updates()

    @_ignore_if_not(game_state='ACTIVE', cell_state=CellNum)
    def chord_on_cell(self, coord):
        """See AbstractController."""

        super().chord_on_cell(coord)

        nbrs = self.board.get_nbrs(coord)
        num_flagged_nbrs = sum(
            [self.board[c] for c in nbrs
             if isinstance(self.board[c], CellMineType)])
        logger.debug("%s flagged mine(s) around clicked cell showing number %d",
                     num_flagged_nbrs, self.board[coord])

        unclicked_nbrs = [c for c in nbrs if self.board[c] == CellUnclicked()]
        if self.board[coord] != CellNum(num_flagged_nbrs) or not unclicked_nbrs:
            return

        logger.info("Successful chording, selecting cells %s", unclicked_nbrs)
        for c in unclicked_nbrs:
            self._select_cell_action(c)

        if self.game_state != GameState.LOST:
            self._check_for_completion()

        self._send_callback_updates()

    @_ignore_if_not(game_state=('READY', 'ACTIVE'), cell_state=CellFlag)
    def remove_cell_flags(self, coord):
        """See AbstractController."""
        
        super().remove_cell_flags(coord)
        
        self.mines_remaining += self.board[coord]
        self._set_cell(coord, CellUnclicked())
        
        self._send_callback_updates()
        
    # def change_settings(self, **kwargs):
    #     """See AbstractController."""
    #     # @@@LG
    #     super().change_settings(**kwargs)

    def resize_board(self, *, x_size, y_size, mines):
        """See AbstractController."""
        super().resize_board(x_size, y_size, mines)
        
        logger.info(
            "Resizing board from %sx%s with %s mines to %sx%s with %s mines",
            self.opts.x_size, self.opts.y_size, self.opts.mines,
            x_size, y_size, mines)
        self.game_state = GameState.INVALID
        self.opts.x_size, self.opts.y_size = x_size, y_size
        self.opts.mines = mines
        self.board = Board(x_size, y_size)
        
        self.new_game()

        #@@@LG Send update to frontends...
            
    # --------------------------------------------------------------------------
    # Helper methods
    # --------------------------------------------------------------------------
    def _init_game(self):
        """
        Initialise the game state.
        """
        self.game_state      = GameState.READY
        self.mines_remaining = self.opts.mines
        self.lives_remaining = self.opts.lives
        self.start_time      = None
        self.end_time        = None
        
    def _select_cell_action(self, coord):
        """
        Perform the action of selecting a cell.
        """
        if self.mf.cell_contains_mine(coord):
            logger.debug("Mine hit at %s", coord)
            self._set_cell(coord, CellHitMine(self.mf[coord]))
            self.lives_remaining -= 1
            
            if self.lives_remaining == 0:
                self.end_time = tm.time()
                logger.info("Game lost")
                self.game_state = GameState.LOST

                for c in self.mf.all_coords:
                    if (self.mf.cell_contains_mine(c) and
                        self.board[c] == CellUnclicked()):
                        self._set_cell(c, CellMine(self.mf[c]))

                    elif (type(self.board[c]) is CellFlag and
                          self.board[c] != self.mf.completed_board[c]):
                        self._set_cell(c, CellWrongFlag(self.board[c]))
                        
        elif self.mf.completed_board[coord] == CellNum(0):
            for full_opening in self.mf.openings:
                if coord in full_opening:
                    # Found the opening, quit the loop here.
                    logger.debug("Opening hit: %s", full_opening)
                    break
            else:
                logger.error("Coordinate %s not found in openings %s",
                             coord, self.mf.openings)

            # Get the propagation of cells forming part of the opening.
            opening = set()  # Coords belonging to the opening
            check = {coord}  # Coords whose neighbours need checking
            while check:
                c = check.pop()
                unclicked_nbrs = {
                    z for z in self.board.get_nbrs(c, include_origin=True)
                    if self.board[z] == CellUnclicked()}
                check |= {z for z in unclicked_nbrs - opening
                          if self.mf.completed_board[z] == CellNum(0)}
                opening |= unclicked_nbrs

            logger.debug("Propagated opening: %s", list(opening))
            bad_opening_cells = {}
            for c in opening:
                if self.board[c] == CellUnclicked():
                    self._set_cell(c, self.mf.completed_board[c])
                else:
                    bad_opening_cells[c] = self.board[c]
            if bad_opening_cells:
                logger.error(
                    "Should only have clicked cells in opening, found: %s",
                    bad_opening_cells)
                    
        else:
            logger.debug("Regular cell revealed")
            self._set_cell(coord, self.mf.completed_board[coord])
                            
    def _set_cell(self, coord, state):
        """
        Set a cell to be in the given state, storing the change to be sent to
        the UI when _send_callback_updates() is called.
        """
        if self.board[coord] == state:
            return

        self.board[coord] = state
        self._cell_updates[coord] = state
                        
    def _check_for_completion(self):
        """
        Check if game is complete by comparing the board to the minefield's
        completed board.
        """
        # Assume (for contradiction) that game is complete.
        is_complete = True
        for c in self.mf.all_coords:
            exp_val = self.mf.completed_board[c]
            if type(exp_val) is CellNum and exp_val != self.board[c]:
                is_complete = False
                break
                
        if is_complete:
            self.end_time = tm.time()
            logger.info("Game won")
            self.game_state = GameState.WON
            self.mines_remaining = 0
            for c in self.mf.all_coords:
                if (self.mf.cell_contains_mine(c) and
                    type(self.board[c]) is not CellHitMine):
                    self._set_cell(c, CellFlag(self.mf[c]))
                    
    # def _split_cell(self, coord):
    #     """
    #     Split a cell.
    #     """
    #     raise NotImplementedError()
    
    def _send_callback_updates(self):
        """See AbstractController."""

        if not self._cell_updates:
            return

        super()._send_callback_updates()
        
        SharedInfo.cell_updates = self._cell_updates
        SharedInfo.game_state = self.game_state
        SharedInfo.mines_remaining = self.mines_remaining
        if self.game_state in ['WON', 'LOST']:
            SharedInfo.elapsed_time = self.end_time - self.start_time
        else:
            SharedInfo.elapsed_time = None

        for cb in self._registered_callbacks:
            try:
                cb(SharedInfo)
            except Exception as e:
                logger.warning("Encountered an error sending an update: %s", e)
            
        self._cell_updates = {}
