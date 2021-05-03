# April 2018, Lewis Gaul

"""
Base GUI application implementation.

Exports
-------
.. class:: MinegaulerGUI
    Main window widget.

"""

__all__ = ("MinegaulerGUI",)

import logging
import os
import pathlib
import textwrap
import traceback
from typing import Callable, Dict, Mapping, Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFocusEvent, QFont, QIcon, QKeyEvent
from PyQt5.QtWidgets import (
    QWIDGETSIZE_MAX,
    QAction,
    QActionGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import ROOT_DIR, shared
from ..core import api
from ..shared.highscores import (
    HighscoreSettingsStruct,
    HighscoreStruct,
    retrieve_highscores,
)
from ..shared.types import (
    CellContents,
    CellImageType,
    Coord_T,
    Difficulty,
    GameState,
    PathLike,
    UIMode,
)
from ..shared.utils import GUIOptsStruct, format_timestamp
from . import highscores, minefield, panel, simulate, state, utils
from .utils import FILES_DIR, HIGHSCORES_DIR, read_highscore_file, save_highscore_file


logger = logging.getLogger(__name__)

BOARD_DIR = ROOT_DIR / "boards"


def _msg_popup(
    parent: QWidget, icon: QMessageBox.Icon, title: str, msg: Optional[str] = None
) -> None:
    """Open a modal popup with a simple message."""
    logger.debug(
        "Opening popup with message: %s", msg if len(msg) <= 50 else msg[:47] + "..."
    )
    popup = QMessageBox(parent)
    popup.setIcon(icon)
    popup.setWindowTitle(title)
    if msg:
        popup.setText(msg)
    popup.exec_()


class _BaseMainWindow(QMainWindow):
    """
    Base class for the application implementing the general layout.
    """

    BODY_FRAME_WIDTH = 10

    def __init__(self, parent: Optional[QWidget], title: Optional[str] = None):
        """
        :param title:
            The window title.
        """
        super().__init__(parent)
        self._menubar: QMenuBar = self.menuBar()
        self._game_menu: QMenu = self._menubar.addMenu("Game")
        self._opts_menu: QMenu = self._menubar.addMenu("Options")
        self._help_menu: QMenu = self._menubar.addMenu("Help")
        self._panel_frame: QFrame
        self._body_frame: QFrame
        self._footer_frame: QFrame
        self._panel_widget: Optional[QWidget]
        self._body_widget: Optional[QWidget]
        self._footer_widget: Optional[QWidget]
        self._icon: QIcon = QIcon(str(utils.IMG_DIR / "icon.ico"))
        self.setWindowTitle(title)
        self.setWindowIcon(self._icon)
        # Disable maximise button
        self.setWindowFlags(self.windowFlags() | Qt.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)
        self._setup_ui()
        # Keep track of all non-modal subwindows that are open.
        self._open_subwindows: Dict[str, QWidget] = {}

    # --------------------------------------------------------------------------
    # UI setup
    # --------------------------------------------------------------------------
    def _setup_ui(self):
        """
        Set up the layout of the main window GUI.
        """
        # QMainWindow objects have a central widget to be set.
        central_widget = QWidget(self)
        central_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setCentralWidget(central_widget)
        vlayout = QVBoxLayout(central_widget)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(0)
        # Top panel widget.
        self._panel_frame = QFrame(central_widget)
        self._panel_frame.setFrameShadow(QFrame.Sunken)
        self._panel_frame.setFrameShape(QFrame.Panel)
        self._panel_frame.setLineWidth(2)
        self._panel_frame.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        vlayout.addWidget(self._panel_frame)
        # Main body widget config - use horizontal layout for centre alignment.
        hstretch = QHBoxLayout()
        hstretch.addStretch()  # left-padding for centering
        self._body_frame = QFrame(central_widget)
        self._body_frame.setFrameShadow(QFrame.Raised)
        self._body_frame.setFrameShape(QFrame.Box)
        self._body_frame.setLineWidth(self.BODY_FRAME_WIDTH // 2)
        hstretch.addWidget(self._body_frame)
        hstretch.addStretch()  # right-padding for centering
        vlayout.addLayout(hstretch)
        # Name entry bar underneath the minefield
        self._footer_frame = QFrame(central_widget)
        vlayout.addWidget(self._footer_frame)

    def set_panel_widget(self, widget: QWidget) -> None:
        """
        Set the widget to occupy the top panel.

        Arguments:
        widget (QWidget)
            The widget instance to place in the top panel.
        """
        lyt = QVBoxLayout(self._panel_frame)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(widget)
        self._panel_widget = widget

    def set_body_widget(self, widget: QWidget) -> None:
        """
        Set the widget to occupy the main section of the GUI.

        Arguments:
        widget (QWidget)
            The widget instance to place in the body.
        """
        lyt = QVBoxLayout(self._body_frame)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(widget)
        self._body_widget = widget

    def set_footer_widget(self, widget: QWidget) -> None:
        """
        Set the widget to occupy the lower bar of the GUI.

        Arguments:
        widget (QWidget)
            The widget instance to place in the lower bar.
        """
        lyt = QVBoxLayout(self._footer_frame)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(widget)
        self._footer_widget = widget


class _MinegaulerGUIMeta(type(api.AbstractListener), type(_BaseMainWindow)):
    """Combined metaclass for the MinegaulerGUI class."""


class MinegaulerGUI(
    api.AbstractListener, _BaseMainWindow, metaclass=_MinegaulerGUIMeta
):
    """The main Minegauler GUI window."""

    def __init__(self, ctrlr: api.AbstractController, initial_state: state.State):
        """
        :param ctrlr:
            The core controller.
        :param initial_state:
            Initial application state.
        """
        super().__init__(None, "Minegauler")
        self._ctrlr: api.AbstractController = ctrlr
        self._state: state.State = initial_state.deepcopy()

        self._create_menu_action: QAction
        self._diff_menu_actions: Dict[Difficulty, QAction] = dict()
        self._populate_menubars()
        self._menubar.setFixedHeight(self._menubar.sizeHint().height())
        self._panel_widget = panel.PanelWidget(self, self._state)
        self._mf_widget = minefield.MinefieldWidget(self, self._ctrlr, self._state)
        self.set_panel_widget(self._panel_widget)
        self.set_body_widget(self._mf_widget)
        self._name_entry_widget = _NameEntryBar(self, self._state.name)
        self.set_footer_widget(self._name_entry_widget)
        self._update_size()

        self._panel_widget.clicked.connect(self._ctrlr.new_game)
        self._mf_widget.at_risk_signal.connect(self._panel_widget.at_risk)
        self._mf_widget.no_risk_signal.connect(self._panel_widget.no_risk)
        self._mf_widget.size_changed.connect(self._update_size)
        self._name_entry_widget.name_updated_signal.connect(self._set_name)

    # ----------------------------------
    # Implemented abstractmethods
    # ----------------------------------
    def reset(self) -> None:
        """
        Called to indicate the GUI state should be soft-reset.

        This is distinct from a factory reset (settings are not changed).
        """
        self._state.game_status = GameState.READY
        self._panel_widget.reset()
        self._mf_widget.reset()

    def resize_minefield(self, x_size: int, y_size: int) -> None:
        """
        Called to indicate the board shape has changed.

        :param x_size:
            The number of columns.
        :param y_size:
            The number of rows.
        """
        # Game state needs updating first for state changes to be applied.
        if self._state.game_status is not GameState.READY:
            self.reset()
        self._state.x_size = x_size
        self._state.y_size = y_size
        self._mf_widget.reshape(x_size, y_size)
        self._diff_menu_actions[self._state.difficulty].setChecked(True)

    def set_mines(self, mines: int) -> None:
        """
        Called to indicate the base number of mines has changed.

        :param mines:
            The number of mines.
        """
        self._state.mines = mines
        self._diff_menu_actions[self._state.difficulty].setChecked(True)

    def update_cells(self, cell_updates: Mapping[Coord_T, CellContents]) -> None:
        """
        Called to indicate some cells have changed state.

        :param cell_updates:
            A mapping of cell coordinates to their new state.
        """
        self._mf_widget.update_cells(cell_updates)

    def update_game_state(self, game_state: GameState) -> None:
        """
        Called to indicate the game state has changed.

        :param game_state:
            The new game state.
        """
        self._state.game_status = game_state
        self._state.highscores_state.current_highscore = None
        self._panel_widget.update_game_state(game_state)
        if game_state.finished():
            self._handle_finished_game()

    def update_mines_remaining(self, mines_remaining: int) -> None:
        """
        Called to indicate the number of remaining mines has changed.

        :param mines_remaining:
            The remaining number of mines.
        """
        self._panel_widget.set_mines_counter(mines_remaining)

    def ui_mode_changed(self, mode: UIMode) -> None:
        """
        Called to indicate the UI mode has changed.

        :param mode:
            The mode to change to.
        """
        self._create_menu_action.setChecked(mode is UIMode.CREATE)

    def handle_exception(self, method: str, exc: Exception) -> None:
        logger.error(
            "Error occurred when calling %s() from backend:\n%s\n%s",
            method,
            "".join(traceback.format_exception(None, exc, exc.__traceback__)),
            exc,
        )
        raise RuntimeError(exc).with_traceback(exc.__traceback__)

    # --------------------------------------------------------------------------
    # Qt method overrides
    # --------------------------------------------------------------------------
    def sizeHint(self) -> QSize:
        width = self._body_frame.sizeHint().width()
        height = (
            self._menubar.sizeHint().height()
            + self._panel_frame.sizeHint().height()
            + self._body_frame.sizeHint().height()
            + self._name_entry_widget.sizeHint().height()
        )
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:
        width = self._panel_frame.minimumSizeHint().width()
        height = (
            self._menubar.sizeHint().height()
            + self._panel_frame.sizeHint().height()
            + 100
            + self._name_entry_widget.sizeHint().height()
        )
        return QSize(width, height)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._name_entry_widget.clearFocus()

    # --------------------------------------------------------------------------
    # Other methods
    # --------------------------------------------------------------------------
    def _update_size(self):
        """Update the window size."""
        self.setMinimumSize(self.minimumSizeHint())
        self.setMaximumSize(self.sizeHint())
        self.resize(self.sizeHint())
        self.adjustSize()
        # print(self.sizeHint(), self.size())
        # print(self._menubar.sizeHint(), self._menubar.size())
        # print(self._panel_frame.sizeHint(), self._panel_frame.size())
        # print(self._body_frame.sizeHint(), self._body_frame.size())
        # print(self._mf_widget.sizeHint(), self._mf_widget.size())
        # print()

    def _populate_menubars(self) -> None:
        """Fill in the menubars."""
        # ----------
        # Game menu
        # ----------
        # New game (F2)
        new_game_act = self._game_menu.addAction("New game", self._ctrlr.new_game)
        new_game_act.setShortcut("F2")

        # Replay game (F3)
        replay_act = self._game_menu.addAction("Replay", self._ctrlr.restart_game)
        replay_act.setShortcut("F3")

        # Create board
        def switch_create_mode(checked: bool):
            mode = UIMode.CREATE if checked else UIMode.GAME
            self._state.ui_mode = mode
            self._ctrlr.switch_mode(mode)

        self._create_menu_action = create_act = QAction(
            "Create board",
            self,
            checkable=True,
            checked=self._state.ui_mode is UIMode.CREATE,
        )
        self._game_menu.addAction(create_act)
        create_act.triggered.connect(switch_create_mode)

        # Save board
        self._game_menu.addAction("Save board", self._open_save_board_modal)

        # Load board
        self._game_menu.addAction("Load board", self._open_load_board_modal)

        self._game_menu.addSeparator()

        # Current info (F4)
        info_act = self._game_menu.addAction(
            "Current game info", self._open_current_info_modal
        )
        info_act.setShortcut("F4")

        # Solver
        # - Probabilities (F5)
        # - Auto flag (Ctrl+F)
        # - Auto click (Ctrl+Enter)

        # Highscores (F6)
        highscores_act = self._game_menu.addAction(
            "Highscores", self.open_highscores_window
        )
        highscores_act.setShortcut("F6")

        # Stats (F7)

        self._game_menu.addSeparator()

        # Difficulty radiobuttons
        # - Beginner (b)
        # - Intermediate (i)
        # - Expert (e)
        # - Master (m)
        # - Custom (c)
        diff_group = QActionGroup(self)
        diff_group.setExclusive(True)
        for diff in Difficulty:
            diff_act = QAction(diff.name.capitalize(), diff_group, checkable=True)
            self._diff_menu_actions[diff] = diff_act
            self._game_menu.addAction(diff_act)
            diff_act.id = diff
            if diff is self._state.difficulty:
                diff_act.setChecked(True)
            diff_act.triggered.connect(
                lambda _: self._change_difficulty(diff_group.checkedAction().id)
            )
            diff_act.setShortcut(diff.value)

        self._game_menu.addSeparator()

        # Play highscore
        # self._game_menu.addAction("Play highscore", self._open_play_highscore_modal)

        # Zoom
        self._game_menu.addAction("Button size", self._open_zoom_modal)

        # Styles
        # - Buttons
        # - Images
        # - Numbers
        def get_change_style_func(grp, style):
            def change_style():
                self._state.styles[grp] = style
                self._mf_widget.update_style(grp, style)

            return change_style

        styles_menu = QMenu("Styles", self)
        self._game_menu.addMenu(styles_menu)
        for img_group in [CellImageType.BUTTONS]:
            img_group_name = img_group.name.capitalize()
            submenu = QMenu(img_group_name, self)
            styles_menu.addMenu(submenu)
            group = QActionGroup(self)
            group.setExclusive(True)
            for folder in (utils.IMG_DIR / img_group_name).glob("*"):
                style = folder.name
                style_act = QAction(style, self, checkable=True)
                if style == self._state.styles[img_group]:
                    style_act.setChecked(True)
                group.addAction(style_act)
                style_act.triggered.connect(get_change_style_func(img_group, style))
                submenu.addAction(style_act)

        # Advanced options
        self._game_menu.addAction("Advanced options", self._open_advanced_opts_modal)

        self._game_menu.addSeparator()

        # Exit (F4)
        self._game_menu.addAction("Exit", self.close, shortcut="Alt+F4")

        # ----------
        # Options menu
        # ----------
        # First-click success
        def toggle_first_success():
            new_val = not self._state.pending_first_success
            self._state.first_success = new_val
            self._ctrlr.set_first_success(new_val)

        first_act = QAction(
            "Safe start", self, checkable=True, checked=self._state.first_success
        )
        self._opts_menu.addAction(first_act)
        first_act.triggered.connect(toggle_first_success)

        # Drag select
        drag_act = self._opts_menu.addAction(
            "Drag select",
            lambda: setattr(
                self._state, "drag_select", not self._state.pending_drag_select
            ),
        )
        drag_act.setCheckable(True)
        drag_act.setChecked(self._state.drag_select)

        # Max mines per cell option
        def get_change_per_cell_func(n):
            def change_per_cell():
                self._state.per_cell = n
                self._ctrlr.set_per_cell(n)

            return change_per_cell

        per_cell_menu = self._opts_menu.addMenu("Max per cell")
        per_cell_group = QActionGroup(self)
        per_cell_group.setExclusive(True)
        for i in range(1, 4):
            action = QAction(str(i), self, checkable=True)
            per_cell_menu.addAction(action)
            per_cell_group.addAction(action)
            if self._state.per_cell == i:
                action.setChecked(True)
            action.triggered.connect(get_change_per_cell_func(i))

        # ----------
        # Help menu
        # ----------
        rules_act = QAction("Rules", self)
        self._help_menu.addAction(rules_act)
        rules_act.triggered.connect(
            lambda: self._open_text_popup("Rules", FILES_DIR / "rules.txt")
        )

        tips_act = QAction("Tips", self)
        self._help_menu.addAction(tips_act)
        tips_act.triggered.connect(
            lambda: self._open_text_popup("Tips", FILES_DIR / "tips.txt")
        )

        retrieve_act = QAction("Retrieve highscores", self)
        retrieve_act.triggered.connect(self._open_retrieve_highscores_modal)
        self._help_menu.addAction(retrieve_act)

        self._help_menu.addSeparator()

        about_act = QAction("About", self)
        self._help_menu.addAction(about_act)
        about_act.triggered.connect(
            lambda: self._open_text_popup("About", FILES_DIR / "about.txt")
        )
        about_act.setShortcut("F1")

        app_specific_feature = QAction("App Specific Feature", self)
        self._help_menu.addAction(app_specific_feature)

    def _change_difficulty(self, diff: Difficulty) -> None:
        """
        Change the difficulty via the core controller.

        :param diff:
            The difficulty.
        """
        if diff is Difficulty.CUSTOM:
            # Undo changing the menu radiobutton because the board hasn't been
            # changed yet.
            self._diff_menu_actions[self._state.difficulty].setChecked(True)
            logger.info("Opening popup window for selecting custom board")
            self._open_custom_board_modal()
            return
        else:
            x, y, m = diff.get_board_values()
            self._ctrlr.resize_board(x_size=x, y_size=y, mines=m)

    def _set_name(self, name: str) -> None:
        self._state.name = name
        self._state.highscores_state.name_hint = name

    def _handle_finished_game(self) -> None:
        """Called once when a game ends."""
        info: api.GameInfo = self._ctrlr.get_game_info()
        assert info.game_state.finished()
        assert info.started_info is not None

        self._panel_widget.timer.set_time(int(info.started_info.elapsed + 1))

        # Store the highscore if the game was won.
        if (
            info.game_state is GameState.WON
            and info.difficulty is not Difficulty.CUSTOM
            and not info.minefield_known
        ):
            assert info.started_info.prop_complete == 1
            highscore = HighscoreStruct(
                difficulty=info.difficulty,
                per_cell=info.per_cell,
                timestamp=int(info.started_info.start_time),
                elapsed=info.started_info.elapsed,
                bbbv=info.started_info.bbbv,
                bbbvps=info.started_info.bbbvps,
                drag_select=self._state.drag_select,
                name=self._state.name,
                flagging=info.started_info.prop_flagging,
            )
            try:
                shared.highscores.insert_highscore(highscore)
            except Exception:
                logger.exception("Error inserting highscore")
            self._state.highscores_state.current_highscore = highscore
            # Check whether to pop up the highscores window.
            # TODO: This is too slow...
            try:
                new_best = shared.highscores.is_highscore_new_best(
                    highscore, shared.highscores.get_highscores(settings=highscore)
                )
            except Exception:
                logger.exception("Error getting highscores")
            else:
                if new_best:
                    self.open_highscores_window(highscore, new_best)
                    # try:
                    #     save_highscore_file(
                    #         highscore, self._mf_widget.get_mouse_events(),
                    #     )
                    # except IOError:
                    #     logger.exception("Error saving highscore to file")

    def _open_save_board_modal(self) -> None:
        if not (
            self._state.game_status.finished() or self._state.ui_mode is UIMode.CREATE
        ):
            # TODO: The menubar option should be disabled.
            return
        file, _ = QFileDialog.getSaveFileName(
            self,
            caption="Save board",
            directory=str(BOARD_DIR),
            filter="Minegauler boards (*.mgb)",
        )
        if not file:
            return
        elif not file.endswith(".mgb"):
            file += ".mgb"
        logger.info("Board requested to be saved at %s", file)
        try:
            self._ctrlr.save_current_minefield(file)
        except Exception:
            logger.exception("Error occurred trying to save minefield to file")
            # TODO: Pop up an error message.

    def _open_load_board_modal(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self,
            caption="Load board",
            directory=str(BOARD_DIR),
            filter="Minegauler boards (*.mgb)",
        )
        if not file:
            return
        logger.info("Board requested to be loaded from %s", file)
        try:
            self._ctrlr.load_minefield(file)
        except Exception:
            # TODO: Pop up error message.
            logger.exception("Error occurred trying to load minefield from file")

    def _open_current_info_modal(self) -> None:
        """Open a popup giving the current game info."""
        info = self._ctrlr.get_game_info()
        _CurrentInfoModal(self, info, self._state).show()

    def _open_custom_board_modal(self) -> None:
        """Open the modal popup to select the custom difficulty."""
        _CustomBoardModal(
            self,
            self._state.x_size,
            self._state.y_size,
            self._state.mines,
            self._ctrlr.resize_board,
        ).show()

    def _open_zoom_modal(self) -> None:
        """Open the popup to set the button size."""
        _ButtonSizeModal(self, self._state.btn_size, self.set_button_size).show()

    def _open_text_popup(self, title: str, file: PathLike):
        """Open a text popup window."""
        if title in self._open_subwindows:
            try:
                self._open_subwindows[title].close()
                # self._open_subwindows[title].setFocus()  # TODO: doesn't work!
                # return
            except Exception:
                self._open_subwindows.pop(title)
        win = _TextPopup(self, title, file)
        win.show()
        self._open_subwindows[title] = win

    def _open_retrieve_highscores_modal(self):
        """Open a window to select a highscores file to read in."""
        accepted = False

        def accept_cb():
            nonlocal accepted
            accepted = True

        logger.debug("Opening window to retrieve highscores")
        dialog = QFileDialog(
            parent=self,
            caption="Retrieve highscores",
            directory=str(pathlib.Path.home()),
            filter="highscores.db",
        )
        dialog.setFileMode(QFileDialog.Directory)
        dialog.accepted.connect(accept_cb)
        dialog.exec_()

        if not accepted:
            return  # cancelled

        path = dialog.selectedFiles()[0]
        logger.debug("Selected directory: %s", path)

        path = pathlib.Path(path)
        if not path.exists():
            _msg_popup(
                self,
                QMessageBox.Critical,
                "Not found",
                "Unable to access selected folder.",
            )
            return

        tail = pathlib.Path()
        for part in reversed(["minegauler", "data", "highscores.db"]):
            tail = part / tail
            if (path / tail).is_file():
                file = path / tail
                break
        else:
            _msg_popup(
                self,
                QMessageBox.Warning,
                "Not found",
                "No highscores database found when searching along the path "
                "'.../minegauler/data/highscores.db'. Contact "
                "minegauler@gmail.com if this error is unexpected.",
            )
            return

        try:
            logger.info("Fetching highscores from %s", file)
            added = retrieve_highscores(file)
            _msg_popup(
                self,
                QMessageBox.Information,
                "Highscores retrieved",
                f"Number of highscores added: {added}",
            )
        except Exception as e:
            _msg_popup(
                self,
                QMessageBox.Critical,
                "Error",
                str(e) + " Contact minegauler@gmail.com if this error is unexpected.",
            )

    def _open_play_highscore_modal(self):
        """Open a modal window to select a highscore file."""
        logger.debug("Opening window to select a highscore to play back")
        hs_file, _ = QFileDialog.getOpenFileName(
            parent=self,
            caption="Play highscore",
            directory=str(HIGHSCORES_DIR),
            filter="Minegauler highscores (*.mgh)",
        )
        logger.debug("Selected file: %s", hs_file)
        if not hs_file:
            return  # cancelled

        hs_file = pathlib.Path(hs_file)
        try:
            hs, cell_updates = read_highscore_file(hs_file)
            x_size, y_size, _ = hs.difficulty.get_board_values()
            win = simulate.SimulationMinefieldWidget(self, x_size, y_size, cell_updates)
        except Exception as e:
            logger.exception("Error reading highscore file")
            _msg_popup(
                self, QMessageBox.Warning, "Error loading highscore file", str(e)
            )
        else:
            win.show()

    def _open_advanced_opts_modal(self):
        _AdvancedOptionsModal(self, self).show()

    def get_gui_opts(self) -> GUIOptsStruct:
        return GUIOptsStruct.from_structs(self._state, self._state.pending_game_state)

    def open_highscores_window(
        self,
        settings: Optional[HighscoreSettingsStruct] = None,
        sort_by: Optional[str] = None,
    ) -> None:
        """
        Open the highscores window.

        :param settings:
            Optionally specify the highscore settings to display highscores
            for. By default the current frontend state is used.
        :param sort_by:
            Optionally specify the key to sort the highscores by. Defaults to
            the previous sort key.
        """
        if self._state.difficulty is Difficulty.CUSTOM:
            return
        if self._open_subwindows.get("highscores"):
            self._open_subwindows.get("highscores").close()
        if not settings:
            settings = HighscoreSettingsStruct(
                difficulty=self._state.difficulty,
                per_cell=self._state.per_cell,
                drag_select=self._state.drag_select,
            )
        if sort_by:
            self._state.highscores_state.sort_by = sort_by
        self._state.highscores_state.name_hint = self._state.name
        win = highscores.HighscoresWindow(self, settings, self._state.highscores_state)
        win.show()
        self._open_subwindows["highscores"] = win

    def set_button_size(self, size: int) -> None:
        """Set the cell size in pixels."""
        self._state.btn_size = size
        self._mf_widget.update_btn_size(size)


class _CurrentInfoModal(QDialog):
    """A popup window with information about the current game."""

    def __init__(self, parent: QWidget, info: api.GameInfo, state_: state.State):
        super().__init__(parent)
        self._info = info
        self._state = state_
        self.setWindowTitle("Game info")
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        base_layout = QVBoxLayout(self)
        base_layout.addWidget(QLabel("Information about the current game:", self))
        info = self._info
        info_text = textwrap.dedent(
            f"""\
            {info.x_size} x {info.y_size} grid
            {info.mines} mines
            Max mines per cell: {info.per_cell}
            Drag-select: {self._state.drag_select}
            """
        )
        if info.game_state.finished():
            assert info.started_info is not None
            fin_info = info.started_info
            start_time = format_timestamp(fin_info.start_time)
            state = info.game_state.name.capitalize()
            info_text += textwrap.dedent(
                f"""\

                Game was started at {start_time}
                {state} after {fin_info.elapsed:.2f} seconds
                The board was {fin_info.prop_flagging * 100:.1f}% flagged
                The 3bv was: {fin_info.bbbv}
                The 3bv/s rate was: {fin_info.bbbvps:.2f}
                """
            )
            if info.game_state is GameState.LOST:
                info_text += textwrap.dedent(
                    f"""\

                    Remaining 3bv: {fin_info.rem_bbbv}
                    Game was {fin_info.prop_complete * 100:.1f}% complete
                    """
                )
                if fin_info.prop_complete > 0:
                    info_text += "Predicted completion time: {:.2f} seconds".format(
                        fin_info.elapsed / fin_info.prop_complete
                    )
        base_layout.addWidget(QLabel(info_text, self))
        ok_btn = QPushButton("Ok", self)
        ok_btn.pressed.connect(self.close)
        base_layout.addWidget(ok_btn)


class _CustomBoardModal(QDialog):
    """A popup window to select custom board dimensions."""

    def __init__(
        self, parent: QWidget, cols: int, rows: int, mines: int, callback: Callable
    ):
        super().__init__(parent)
        self._cols: int = cols
        self._rows: int = rows
        self._mines: int = mines
        self._callback: Callable = callback
        self.setWindowTitle("Custom")
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        base_layout = QVBoxLayout(self)
        base_layout.addWidget(
            QLabel("Select the number of rows, columns and mines.", self)
        )

        # Set up the input sliders and spin boxes.
        grid_layout = QGridLayout()
        base_layout.addLayout(grid_layout)

        def make_row(
            row: int, label: str, current: int, minval: int, maxval: int
        ) -> _SliderSpinner:
            grid_layout.addWidget(QLabel(label, self), row, 0)
            slider = _SliderSpinner(self)
            grid_layout.addWidget(slider, row, 1)
            slider.setValue(current)
            slider.setMinimum(minval)
            slider.setMaximum(maxval)
            return slider

        y_slider = make_row(1, "Rows", self._rows, 2, 50)
        x_slider = make_row(2, "Columns", self._cols, 2, 50)
        m_slider = make_row(3, "Mines", self._mines, 1, self._rows * self._cols - 1)

        def set_mines_max():
            m_slider.setMaximum(x_slider.value() * y_slider.value() - 1)

        x_slider.valueChanged.connect(set_mines_max)
        y_slider.valueChanged.connect(set_mines_max)

        # Ok/Cancel buttons.
        def ok_pressed():
            self._callback(x_slider.value(), y_slider.value(), m_slider.value())
            self.close()

        ok_btn = QPushButton("Ok", self)
        ok_btn.pressed.connect(ok_pressed)
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.pressed.connect(self.close)
        btns_layout = QHBoxLayout()
        base_layout.addLayout(btns_layout)
        btns_layout.addWidget(ok_btn)
        btns_layout.addWidget(cancel_btn)


class _ButtonSizeModal(QDialog):
    """A popup window to select the button size."""

    def __init__(self, parent: QWidget, btn_size: int, callback: Callable):
        super().__init__(parent)
        self.setWindowTitle("Button size")
        self._btn_size: int = btn_size
        self._callback: Callable = callback
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        base_layout = QVBoxLayout(self)
        base_layout.addWidget(QLabel("Select the button size in pixels.", self))

        # Set up the input sliders and spin boxes.
        slider = _SliderSpinner(self)
        slider.setValue(self._btn_size)
        slider.setMinimum(16)
        slider.setMaximum(40)
        base_layout.addWidget(slider)

        # Ok/Cancel buttons.
        def ok_pressed():
            self._callback(slider.value())
            self.close()

        ok_btn = QPushButton("Ok", self)
        ok_btn.pressed.connect(ok_pressed)
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.pressed.connect(self.close)
        btns_layout = QHBoxLayout()
        base_layout.addLayout(btns_layout)
        btns_layout.addWidget(ok_btn)
        btns_layout.addWidget(cancel_btn)


class _AdvancedOptionsModal(QDialog):
    """A popup window to select advanced options."""

    def __init__(self, parent: QWidget, main_window: MinegaulerGUI):
        super().__init__(parent)
        self.setWindowTitle("Advanced options")
        self.setModal(True)
        self._main_window = main_window
        self._setup_ui()

    def _setup_ui(self):
        """Set up the window layout."""
        vlayout = QVBoxLayout(self)
        vlayout.addWidget(
            QLabel("These options are in beta - stability not guaranteed", self)
        )

        def add_opt(label: str, func: Callable):
            hlayout = QHBoxLayout(self)
            vlayout.addLayout(hlayout)
            hlayout.addWidget(QLabel(label, self))
            button = QPushButton("Enable", self)
            button.clicked.connect(func)
            button.clicked.connect(lambda: button.setDisabled(True))
            hlayout.addWidget(button)

        add_opt("Enable main window maximising", self._enable_maximise)

    def _enable_maximise(self):
        """Enable maximising the main window."""
        win = self._main_window

        def update_size():
            win.setMinimumSize(win.minimumSizeHint())
            if not win.isMaximized():
                win.resize(win.sizeHint())
                win.adjustSize()

        win.hide()
        win.setWindowFlag(Qt.WindowMaximizeButtonHint)
        win.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
        win._mf_widget.size_changed.disconnect(win._update_size)
        win._update_size = update_size
        win._mf_widget.size_changed.connect(win._update_size)
        win.show()


class _SliderSpinner(QWidget):
    """A combination of a slider and a spinbox."""

    valueChanged = pyqtSignal(int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slider = QSlider(Qt.Horizontal)
        self.numbox = QSpinBox()
        self.numbox.setRange(self.slider.minimum(), self.slider.maximum())
        self.numbox.setFixedWidth(50)
        self.slider.valueChanged.connect(self.numbox.setValue)
        self.slider.rangeChanged.connect(self.numbox.setRange)
        self.numbox.valueChanged.connect(self.slider.setValue)
        self.slider.valueChanged.connect(self.valueChanged.emit)
        self.valueChanged.connect(self.setValue)
        layout = QHBoxLayout(self)
        layout.addWidget(self.slider)
        layout.addWidget(self.numbox)

    def setMinimum(self, minval: int):
        self.slider.setMinimum(minval)

    def setMaximum(self, maxval: int):
        self.slider.setMaximum(maxval)

    def setValue(self, value: int):
        self.slider.setValue(value)

    def value(self) -> int:
        return self.slider.value()


class _NameEntryBar(QLineEdit):
    """Entry bar for entering a name."""

    name_updated_signal = pyqtSignal(str)

    def __init__(self, parent, text: str = ""):
        super().__init__(parent)
        self.setText(text)
        self.setPlaceholderText("Enter name here")
        self.setAlignment(Qt.AlignCenter)
        font = QFont("Helvetica")
        font.setBold(True)
        self.setFont(font)

    def keyPressEvent(self, event: QKeyEvent):
        super().keyPressEvent(event)
        if event.key() in [Qt.Key_Return, Qt.Key_Enter]:
            self.clearFocus()

    def focusOutEvent(self, event: QFocusEvent):
        super().focusOutEvent(event)
        self.setText(self.text().strip())
        logger.info("Setting name to %r", self.text())
        self.name_updated_signal.emit(self.text())


class _TextPopup(QWidget):
    """A popup window containing a block of text."""

    def __init__(self, parent: Optional[QWidget], title: str, file: PathLike):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window)
        self.setWindowTitle(title)
        self.setMinimumSize(200, 100)

        self._text_widget = QLabel(self)
        self._ok_button = QPushButton(self)
        self._setup_ui()

        with open(file) as f:
            self._text_widget.setText(f.read())

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        lyt = QVBoxLayout(self)
        # lyt.setAlignment(Qt.AlignCenter)

        self._text_widget.setLineWidth(1)
        self._text_widget.setFrameShape(QFrame.Panel)
        self._text_widget.setMargin(10)
        self._text_widget.setStyleSheet(
            """
            background-color: white;
            """
        )
        self._text_widget.setWordWrap(True)
        lyt.addWidget(self._text_widget)

        self._ok_button.setText("Ok")
        self._ok_button.setMaximumWidth(50)
        self._ok_button.clicked.connect(self.close)
        lyt.addWidget(self._ok_button)

    def sizeHint(self) -> QSize:
        size = super().sizeHint()
        area = size.width() * size.height()
        return QSize(int(area ** 0.5), int(area ** 0.4))
