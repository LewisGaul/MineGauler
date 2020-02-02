"""
benchmark_test.py - Benchmark tests

February 2020, Lewis Gaul

Uses pytest-benchmark - simply run 'python -m pytest tests/ [-k benchmark]' from
the root directory.
"""

from pytest_benchmark.fixture import BenchmarkFixture

from minegauler import core
from minegauler.types import CellFlag, CellNum

from .utils import ITBase
from .utils import process_events as _utils_process_events


def process_events():
    _utils_process_events(0)


class TestBenchmarks(ITBase):
    """Benchmark testcases."""

    def setup_method(self):
        self.ctrlr.resize_board(x_size=50, y_size=50, mines=1000)
        process_events()

    def test_new_game(self, benchmark: BenchmarkFixture):
        benchmark(self.ctrlr.new_game)

    def test_restart_game(self, benchmark: BenchmarkFixture):
        benchmark(self.ctrlr.restart_game)

    def test_flag_one_cell(self, benchmark: BenchmarkFixture):
        benchmark(self.ctrlr.flag_cell, (0, 0))

    def test_change_lots_of_cells(self, benchmark: BenchmarkFixture):
        # Create a board with a huge opening, but not resulting in the game
        # being completed in one click.
        checked = False

        def setup():
            nonlocal checked
            mf = core.board.Minefield(x_size=50, y_size=50, mines=[(1, 0)])
            if not checked:
                assert mf.completed_board[(0, 0)] == CellNum(1)
                assert mf.completed_board[(1, 0)] == CellFlag(1)
                assert mf.completed_board[(3, 3)] == CellNum(0)
                checked = True
            self.ctrlr.load_minefield(mf)

        benchmark.pedantic(self.ctrlr.select_cell, ((3, 3),), setup=setup, rounds=10)

    def test_win_game(self, benchmark: BenchmarkFixture):
        # Create a basic one-click win situation.
        checked = False

        def setup():
            nonlocal checked
            mf = core.board.Minefield(x_size=2, y_size=1, mines=[(1, 0)])
            if not checked:
                assert mf.completed_board[(0, 0)] == CellNum(1)
                assert mf.completed_board[(1, 0)] == CellFlag(1)
                checked = True
            self.ctrlr.load_minefield(mf)

        benchmark.pedantic(self.ctrlr.select_cell, ((0, 0),), setup=setup)

    def test_lose_game(self, benchmark: BenchmarkFixture):
        # Create a basic one-click lose situation.
        checked = False

        def setup():
            nonlocal checked
            mf = core.board.Minefield(x_size=2, y_size=1, mines=[(1, 0)])
            if not checked:
                assert mf.completed_board[(0, 0)] == CellNum(1)
                assert mf.completed_board[(1, 0)] == CellFlag(1)
                checked = True
            self.ctrlr.load_minefield(mf)

        benchmark.pedantic(self.ctrlr.select_cell, ((1, 0),), setup=setup)
