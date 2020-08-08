# August 2020, Lewis Gaul

"""
CLI entry-point.

"""

import logging
import os
import pathlib
import re
import subprocess as sp
import sys
import traceback
from typing import Optional, Union

# Any 3rd-party dependencies must be kept in bootstrap/.
import yaml

from .parser import CLIParser


_THIS_DIR = pathlib.Path(__file__).parent
_PROJECT_DIR = _THIS_DIR.parent
_VENV_DIR = _PROJECT_DIR / ".venv"

logger = logging.getLogger(__name__)

PathLike = Union[str, pathlib.Path]


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------


class UserFacingError(Exception):
    """An error with a representation that may be shown to the user."""

    def __init__(self, user_msg: str, exit_code: int = 1):
        super().__init__(user_msg)
        self.exit_code = exit_code


def _is_version_at_least(version: str, major: int, minor: Optional[int] = None) -> bool:
    parts = version.split(".", maxsplit=3)
    if int(parts[0]) < major:
        return False
    if minor and int(parts[1]) < minor:
        return False
    return True


def _find_venv_python(path: PathLike) -> str:
    """Look for python executable in venv."""
    path = pathlib.Path(path)
    if path.is_dir():
        for exe_paths in ["bin/python", "Scripts/python.exe"]:
            if (path / exe_paths).is_file():
                path /= exe_paths
                break
    if not path.is_file():
        raise FileNotFoundError("Python executable not found at %s", path)
    return str(path)


def _check_python_capabilities(location: Optional[PathLike] = None) -> Optional[str]:
    """
    Check the basic Python capabilities (version and stdlib modules).

    :param location:
        The path to a virtualenv directory or python executable to check, or
        None to check the one in use.
    :raises FileNotFoundError:
        If a Python executable can't be found at the given location.
    :raises UserFacingError:
        If the Python capabilities are insufficient.
    :return:
        If 'location' was given, the path to the python executable is returned,
        otherwise None.
    """
    if location is None:
        # Check version (3.6+ required).
        if not _is_version_at_least(sys.version, 3, 6):
            raise UserFacingError(
                "Python3.6+ required, detected {}".format(sys.version)
            )
        # Check venv capability.
        try:
            import venv
        except ImportError:
            raise UserFacingError(
                "The standard library 'venv' module could not be found"
            )
        return
    else:
        if os.path.isfile(location):
            python_exe = str(location)
        else:
            python_exe = _find_venv_python(location)
        # Check venv Python version.
        try:
            proc = sp.run(
                [python_exe, "--version"],
                stdout=sp.PIPE,
                stderr=sp.PIPE,
                universal_newlines=True,
                check=True,
                timeout=1,
            )
            version = re.match(r"Python (\d\.\d+\.\d+\S*)", proc.stdout).group(1)
        except (sp.CalledProcessError, sp.TimeoutExpired):
            raise UserFacingError("Unable to determine Python version")
        except AttributeError:
            logger.debug(
                "Unexpected output from '%s --version':\n%s", python_exe, proc.output
            )
            raise UserFacingError("Unable to determine Python version")
        else:
            if not _is_version_at_least(version, 3, 6):
                raise UserFacingError(
                    "Python3.6+ required, detected {}".format(version)
                )
        try:
            sp.run(
                [python_exe, "-m", "pip", "--version"],
                stdout=sp.PIPE,
                stderr=sp.PIPE,
                universal_newlines=True,
                check=True,
                timeout=3,
            )
        except (sp.CalledProcessError, sp.TimeoutExpired):
            raise UserFacingError("Pip doesn't seem to be available")
        return python_exe


def _check_venv(path: PathLike) -> str:
    """
    Check the given virtualenv is set up correctly.

    :param path:
        Path to virtualenv directory.
    :return:
        Path to python executable within the virtualenv.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError("venv directory not found")
    try:
        python_exe = _check_python_capabilities(path)
    except FileNotFoundError:
        raise UserFacingError(
            "There is already a '.venv' directory which doesn't seem to be "
            "a virtual environment. Can it be moved/deleted?"
        )
    except UserFacingError as e:
        raise UserFacingError(
            "There is a problem with the existing virtual environment: " + str(e)
        )
    return python_exe


# ------------------------------------------------------------------------------
# Command functions
# ------------------------------------------------------------------------------


def run_app(args):
    python_exe = _find_venv_python(_VENV_DIR)
    print(python_exe)
    # @@@ Check venv.
    sp.run([python_exe, "-m", "minegauler"])


def make_venv(args):
    print("INFO: Checking Python capabilities...")
    _check_python_capabilities()

    try:
        python_exe = _check_venv(_VENV_DIR)
        print("INFO: Found existing virtual environment")
    except FileNotFoundError:
        print("INFO: Creating virtual environment...")
        # Create venv.
        import venv

        venv.create(_VENV_DIR, with_pip=True)
        python_exe = _check_venv(_VENV_DIR)
        print("INFO: Virtual environment successfully created")

    # Check requirements are satisfied, do pip install.
    if args.check:
        raise UserFacingError("The 'check' flag is not yet implemented")
    else:
        if args.dev:
            req_file = _PROJECT_DIR / "requirements-dev.txt"
        else:
            req_file = _PROJECT_DIR / "requirements.txt"
        print("INFO: Installing project requirements...")
        try:
            sp.run(
                [python_exe, "-m", "pip", "install", "-r", str(req_file)],
                stdout=sp.PIPE,
                stderr=sp.PIPE,
                universal_newlines=True,
                check=True,
            )
            print("INFO: Project requirements successfully installed")
        except sp.CalledProcessError:
            raise UserFacingError("Error installing project requirements")


def run_tests(args):
    # TODO: Use the venv python.
    # The double dash can be used to pass args through to pytest.
    try:
        args.remaining_args.remove("--")
    except ValueError:
        pass
    if args.pytest_help:
        sp.run(["python", "-m", "pytest", "-h"])
    else:
        sp.run(["python", "-m", "pytest"] + args.remaining_args)


def run_bot_cli(args):
    import bot

    bot.utils.read_users_file()

    try:
        args.remaining_args.remove("--")
    except ValueError:
        pass
    return bot.msgparse.main(args.remaining_args)


def add_bot_player(args):
    import bot.utils

    bot.utils.read_users_file()
    bot.utils.set_user_nickname(args.player_name, args.player_name)


def remove_bot_player(args):
    import bot.utils

    bot.utils.read_users_file()
    bot.utils.USER_NAMES.pop(args.player_name)
    bot.utils.save_users_file()


_COMMANDS = {
    "run": run_app,
    "make-venv": make_venv,
    "run-tests": run_tests,
    "bump-version": lambda args: print("Not implemented"),
    "bot": run_bot_cli,
    "bot-add-player": add_bot_player,
    "bot-remove-player": remove_bot_player,
}


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------


def main(argv) -> int:
    # Load the CLI schema.
    with open(str(_THIS_DIR / "cli.yaml")) as f:
        schema = yaml.safe_load(f)

    # Parse argv.
    prog = "run.bat" if sys.platform.startswith("win") else "run.sh"
    args = CLIParser(schema, prog=prog).parse_args(argv)
    logger.debug("Got args:", args)

    # Run the command!
    try:
        _COMMANDS[args.command](args)
        return 0
    except UserFacingError as e:
        print("ERROR:", e, file=sys.stderr)
        return e.exit_code
    except Exception as e:
        print(
            "ERROR: Unexpected error, please contact the maintainer to sort this out!",
            file=sys.stderr,
        )
        with open(".last_error.txt", "w") as f:
            traceback.print_exception(None, e, e.__traceback__, file=f)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
