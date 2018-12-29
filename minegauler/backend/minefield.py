"""
minefield.py - Implementation of a minefield object

March 2018, Lewis Gaul

Exports:
Minefield (class)
    A grid initialised with a random number of mines in each cell.
"""

import logging
import random as rnd

from minegauler.backend.utils import Grid, Board
from minegauler.shared.internal_types import CellNum, CellFlag


logger = logging.getLogger(__name__)


class Minefield(Grid):
    """
    Grid representation of a minesweeper minefield, each cell contains an
    integer representing the number of mines at that cell.
    
    Inherits minegauler.backend.utils.Grid
    
    Attributes:
    mines (int >= 0)
        Number of mines.
    per_cell (int > 0)
        Maximum number of mines per cell.
    is_created (bool)
        Whether the minefield has been created or not.
    mine_coords ([(int, int), ...])
         List of mine coordinates in (x, y) format.
    completed_board (Board)
        Grid containing the state of the board when the minefield is fully
        solved.
    openings ([[(int, int), ...], [...], ...])
        A list of openings, each of which is a list of coordinates which are
        part of the opening, i.e. all the cells which would be revealed if one
        of the cells within the opening was clicked.
    bbbv (int > 0)
        The 3bv of the minefield.
    """

    def __init__(self, x_size, y_size, mines, per_cell=1, *,
                 create=True, safe_coords=None):
        """
        Create a minefield. ValueError is raised if the mines can't fit into
        the available cells, as determined by the list of safe coordinates
        provided along with the other parameters.
        
        Arguments:
        x_size (int > 0)
            Number of columns.
        y_size (int > 0)
            Number of rows.
        mines (int >= 0)
            Number of mines.
        per_cell (int > 0)
            Maximum number of mines per cell.
        create=True (bool)
            Whether to fill in the minefield at initialisation or leave it
            empty.
        safe_coords=None ([(int, int), ...] | None)
            List of coordinates that should not contain a mine when filling the
            minefield. Ignored if not creating the minefield at initialisation.
        """

        if create and safe_coords is not None:
            mine_spaces = x_size * y_size - max(1, len(set(safe_coords)))
        else:
            mine_spaces = x_size * y_size - 1
        if mines > mine_spaces * per_cell:
            raise ValueError(
                f"Number of mines too high ({mines}) "
                f"for grid with {mine_spaces} spaces "
                f"and only up to {per_cell} allowed per cell.")
        # Initialise grid and attributes.
        super().__init__(x_size, y_size)
        self.is_created      = False
        self.mines           = mines
        self.per_cell        = per_cell
        self.mine_coords     = None
        self.completed_board = None
        self.openings        = None
        self.bbbv            = None
        if create:
            self.create(safe_coords)

    def __repr__(self):
        mines_str = f" with {self.mines} mines" if self.mines else ""
        return f"<{self.x_size}x{self.y_size} minefield{mines_str}>"

    @classmethod
    def from_mines_list(cls, x_size, y_size, mine_coords, per_cell=None):
        """
        Create a minefield with a list of coordinates of where mines are to
        lie.
        
        Arguments:
        x_size (int > 0)
            Number of columns for the minefield.
        y_size (int > 0)
            Number of rows for the minefield.
        mine_coords ([(int, int), ...])
            List of mine coordinates, which must fit within the dimensions of
            the minefield.
        per_cell=None (int > 0 | None)
            Optionally specify the maximum number of mines per cell,
            otherwise the maximum number found will be used. If the number of
            occurrences of any of the coordinates in the grid exceeds this
            value, the per_cell value will be increased to accommodate this,
            overriding the passed in value.
            
        Return: Minefield
            The created minefield.
        """
        max_mines_in_cell = max(mine_coords.count(c) for c in mine_coords)
        if not per_cell:
            per_cell = max_mines_in_cell
        elif max_mines_in_cell > per_cell:
            logger.warning(
                "Overriding passed in per_cell value of %d, using %d",
                per_cell, max_mines_in_cell)
            per_cell = max_mines_in_cell

        mf = cls(x_size, y_size, len(mine_coords), per_cell, create=False)
        mf.mine_coords = sorted(mine_coords)
        for c in mine_coords:
            mf[c] += 1
        mf._get_completed_board()
        mf._find_openings()
        mf._calc_3bv()
        mf.is_created = True

        return mf

    @classmethod
    def from_grid(cls, grid, per_cell=None):
        """
        Create a minefield with a grid showing where mines are to lie.

        Arguments:
        grid (Grid)
            The grid of mines.
        per_cell=None (int > 0 | None)
            Optionally specify the maximum number of mines per cell,
            otherwise the maximum number found will be used. If the number of
            occurrences of any of the coordinates in the grid exceeds this
            value, the per_cell value will be increased to accommodate this,
            overriding the passed in value.

        Return: Minefield
            The created minefield.
        """
        mine_coords = []
        for c in grid.all_coords:
            for _ in range(grid[c]):
                mine_coords.append(c)

        return cls.from_mines_list(grid.x_size, grid.y_size, mine_coords,
                                   per_cell)
    
    @classmethod
    def from_2d_array(cls, array, per_cell=None):
        """
        See minegauler.backend.utils.Grid and Minefield.from_grid().
        """
        grid = Grid.from_2d_array(array)
        return cls.from_grid(grid, per_cell)

    def create(self, safe_coords=None):
        """
        Fill in the minefield at random. Also get the completed board and 3bv
        for the created minefield. Raises TypeError if the minefield has already
        been created.
        
        Arguments:
        safe_coords ([(int, int), ...] | None)
            List of coordinates which should not contain any mines.

        Raises:
        TypeError
            - Minefield already created.
        ValueError
            - Not enough space for mines.
        """
        if self.is_created:
            raise TypeError("Minefield already created")
        if safe_coords is not None:
            mine_spaces = len(self.all_coords) - len(set(safe_coords))
            if self.mines > mine_spaces * self.per_cell:
                raise ValueError(
                    f"Number of mines too high ({self.mines}) "
                    f"for grid with {mine_spaces} spaces "
                    f"and only up to {self.per_cell} allowed per cell.")
            
        # Get a list of coordinates which can have mines placed in them.
        if safe_coords is None:
            avble_coords = self.all_coords.copy()
        else:
            avble_coords = [c for c in self.all_coords if c not in safe_coords]
        # Make sure there is at least one safe cell.
        if len(avble_coords) == len(self.all_coords):
            avble_coords.pop(rnd.randint(0, len(avble_coords) - 1))    
        avble_coords *= self.per_cell
        rnd.shuffle(avble_coords)
        self.mine_coords = avble_coords[:self.mines]
        for c in self.mine_coords:
            self[c] += 1
        self._get_completed_board()
        self._find_openings()
        self._calc_3bv()
        self.is_created = True

    def cell_contains_mine(self, coord):
        """
        Return whether a cell contains at least one mine.
        
        Arguments:
        coord ((int, int), within grid boundaries)
            The coordinate to check.
            
        Return: bool
            Whether the cell contains a mine.
        """
        return self[coord] > 0

    def _get_completed_board(self):
        """
        Create and fill the completed board with the flags and numbers that
        should be seen upon game completion.
        """
        self.completed_board = Board(self.x_size, self.y_size)
        self.completed_board.fill(CellNum(0))
        for c in self.all_coords:
            mines = self[c]
            if mines > 0:
                self.completed_board[c] = CellFlag(mines)
                for nbr in self.get_nbrs(c):
                    # For neighbouring cells that don't contain mines, increment
                    #  their number.
                    if not self.cell_contains_mine(nbr):
                        self.completed_board[nbr] += mines

    def _find_openings(self):
        """
        Find the openings of the board. A list of openings is stored, each
        represented as a list of coordinates belonging to that opening.
        Note that each cell cannot belong to multiple openings.
        """
        self.openings = []
        blanks_to_check = {c for c in self.all_coords
                                       if self.completed_board[c] == CellNum(0)}
        while blanks_to_check:
            orig_coord = blanks_to_check.pop()
            # If the coordinate is part of an opening and hasn't already been
            #  considered, start a new opening.
            opening = {orig_coord} # Coords belonging to the opening
            check = {orig_coord}   # Coords whose neighbours need checking
            while check:
                coord = check.pop()
                nbrs = set(self.get_nbrs(coord))
                check |= {c for c in nbrs - opening
                                       if self.completed_board[c] == CellNum(0)}
                opening |= nbrs
            self.openings.append(sorted(opening))
            blanks_to_check -= opening

    def _calc_3bv(self):
        """
        Calculate the 3bv of the board.
        """
        assert self.openings is not None, (
            "Must find openings before 3bv can be calculated.")
        clicks = len(self.openings)
        exposed = len({c for opening in self.openings for c in opening})
        clicks += self.x_size*self.y_size - len(set(self.mine_coords)) - exposed
        self.bbbv = clicks
