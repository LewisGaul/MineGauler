"""
utils.py - Utilities

March 2018, Lewis Gaul

Exports:
Grid (class)
    Representation of a 2D grid using nested lists.
Board (class)
    Representation of a minesweeper board, inheriting from Grid.
"""

import logging
from abc import ABC, abstractmethod

from minegauler.shared.internal_types import *


logger = logging.getLogger(__name__)



class Grid(list):
    """
    Grid representation using a list of lists (2D array).
    
    Attributes:
    x_size (int > 0)
        The number of columns.
    y_size (int > 0)
        The number of rows.
    all_coords ([(int, int), ...])
        List of all coordinates in the grid.
    """
    def __init__(self, x_size, y_size, *, fill=0):
        """
        Arguments:
        x_size (int > 0)
            The number of columns.
        y_size (int > 0)
            The number of rows.
        fill=0 (object)
            What to fill the grid with.
        """
        super().__init__()
        for j in range(y_size):
            row = x_size * [fill]
            self.append(row)
        self.x_size, self.y_size = x_size, y_size
        self.all_coords = [(x, y) for x in range(x_size) for y in range(y_size)]

    def __repr__(self):
        return f"<{self.x_size}x{self.y_size} grid>"

    def __str__(self, mapping=None, cell_size=None):
        """
        Convert the grid to a string in an aligned format. The __repr__ method
        is used to display the objects inside the grid unless the mapping
        argument is given.
        
        Arguments:
        mapping=None (dict | callable | None)
            A mapping to apply to all objects contained within the grid. The
            result of the mapping will be converted to a string and displayed.
            If a mapping is specified, a cell size should also be given.
        cell_size=None (int | None)
            The size to display a grid cell as. Defaults to the maximum size of
            the representation of all the objects contained in the grid.
        """
        #@@@LG Some attention please :)

        # Use max length of object representation if no cell size given.
        if cell_size is None:
            cell_size = max(
                           [len(obj.__repr__()) for row in self for obj in row])

        cell = '{:>%d}' % cell_size
        ret = ''
        for row in self:
            for obj in row:
                if isinstance(mapping, dict):
                    rep = str(mapping[obj]) if obj in mapping else repr(obj)
                elif mapping is not None:
                    rep = str(mapping(obj))
                else:
                    rep = repr(obj)
                ret += cell.format(rep[:cell_size]) + ' '
            ret = ret[:-1]  # Remove trailing space
            ret += '\n'
        ret = ret[:-1]  # Remove trailing newline

        return ret

    def __getitem__(self, key):
        if type(key) is tuple and len(key) == 2:
            return self[key[1]][key[0]]
        else:
            return super().__getitem__(key)

    def __setitem__(self, key, value):
        if type(key) is tuple and len(key) == 2:
            self[key[1]][key[0]] = value
        else:
            super().__setitem__(key, value)

    @classmethod
    def from_2d_array(cls, array):
        """
        Create an instance using a 2-dimensional array.

        Arguments:
        array ([[object, ...], ...])
            The array to use in creating the grid instance.

        Return: Grid
            The resulting grid.
        """
        x_size = len(array[0])
        y_size = len(array)
        grid = cls(x_size, y_size)
        for coord in grid.all_coords:
            x, y = coord
            grid[coord] = array[y][x]
        return grid

    def fill(self, item):
        """
        Fill the grid with a given object.
        
        Arguments:
        item (object)
            The item to fill the grid with.
        """
        for row in self:
            for i in range(len(row)):
                row[i] = item

    def get_nbrs(self, coord, *, include_origin=False):
        """
        Get a list of the coordinates of neighbouring cells.
        
        Arguments:
        coord ((int, int), within grid boundaries)
            The coordinate to check.
        include_origin=False (bool)
            Whether to include the original coordinate, coord, in the list.
            
        Return: [(int, int), ...]
            List of coordinates within the boundaries of the grid.
        """
        x, y = coord
        nbrs = []
        for i in range(max(0, x - 1), min(self.x_size, x + 2)):
            for j in range(max(0, y - 1), min(self.y_size, y + 2)):
                nbrs.append((i, j))
        if not include_origin:
            nbrs.remove(coord)
        return nbrs
        
        
class Board(Grid):
    """
    Representation of a minesweeper board. Can only be filled with objects that
    inherit CellContentsType.
    """
    def __init__(self, x_size, y_size):
        """
        Arguments:
        x_size (int > 0)
            The number of columns.
        y_size (int > 0)
            The number of rows.
        """
        super().__init__(x_size, y_size, fill=CellUnclicked())
        
    def __repr__(self):
        return f"<{self.x_size}x{self.y_size} board>"

    def __str__(self):
        return super().__str__(mapping={CellNum(0): '.'})

    def __setitem__(self, key, value):
        if not isinstance(value, CellContentsType):
            raise TypeError("Board can only contain CellContentsType instances")
        else:
            super().__setitem__(key, value)

    @classmethod
    def from_2d_array(cls, array):
        """
        Create a minesweeper board from a 2-dimensional array of string
        representations for cell contents.

        Arguments:
        array ([[str|int, ...], ...])
            The array to create the board from.

        Return:
            The created board.

        Raises:
        ValueError
            - Invalid string representation of cell contents.
        """
        grid = Grid.from_2d_array(array)
        board = cls(grid.x_size, grid.y_size)
        for c in grid.all_coords:
            if type(grid[c]) is int:
                board[c] = CellNum(grid[c])
            elif type(grid[c]) is str and len(grid[c]) == 2:
                char, num = grid[c]
                board[c] = CellMineType.get_class_from_char(char)(int(num))
            elif grid[c] != CellUnclicked.char:
                raise ValueError(
                    f"Unknown cell contents representation in cell {c}: "
                    f"{grid[c]}")
        return board



class GeneralBoard(ABC):
    def __init__(self):
        self.cells = set()

    @abstractmethod
    def get_nbrs(self, id, *, include_origin=False):
        pass


class SplitCellBoard(GeneralBoard):
    def __init__(self, x_size, y_size):
        self.x_size, self.y_size = x_size, y_size
        super().__init__()
        for i in range(x_size):
            for j in range(y_size):
                self.cells.add(SplittableCell())

    def __repr__(self):
        return f"<{self.x_size}x{self.y_size} split-cell board>"

    def __str__(self):
        row_border = '+' + self.x_size * '-------+'
        lines = [row_border]
        for row in self:
            line1 = '|'
            line2 = '|'
            line3 = '|'
            for big_cell in row:
                #@@@LG Use cell repr (join multiline strings)
                if big_cell.is_split:
                    for i in range(big_cell.subcells.x_size):
                        line1 += ' {:.1} |'.format(
                            str(big_cell.subcells[(i, 0)].contents))
                        line2 += '---+'
                        line3 += ' {:.1} |'.format(
                            str(big_cell.subcells[(i, 1)].contents))
                    line1 = line1[:-1] + '|'
                    line3 = line3[:-1] + '|'
                else:
                    line1 += '       |'
                    line2 += '   {:.1}   |'.format(str(big_cell.contents))
                    line3 += '       |'
            lines.extend([line1, line2, line3, row_border])

        return '\n'.join(lines)

    def get_nbrs(self, id, *, include_origin=False):
        raise NotImplementedError()


class Cell:
    count = 0
    def __init__(self):
        self.id = __class__.count
        __class__.count += 1
        self.contents = CellUnclicked()

    def __repr__(self):
        return f"|{str(self.contents)}|"


class SplittableCell(Cell):
    def __init__(self):
        super().__init__()
        self.subcells = Grid(2, 2)
        for c in self.subcells.all_coords:
            self.subcells[c] = Cell()

    # def __repr__(self):
    #     if self.is_split:
    #         ret = ("+-------+\n"
    #                "| 2 | 1 |\n"
    #                "|---+---|\n"
    #                "| # | F |\n"
    #                "+-------+")
    #     else:
    #         ret = ("+-------+\n"
    #                "|       |\n"
    #                "|   {:.1}   |\n"
    #                "|       |\n"
    #                "+-------+").format(str(self.contents))
    #
    #     return ret