# February 2020, Lewis Gaul

"""
Parse bot messages.

"""

__all__ = ("GENERAL_INFO", "RoomType", "parse_msg")

import argparse
import enum
import logging
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from minegauler.shared import highscores as hs
from minegauler.shared.types import Difficulty

from . import formatter, utils


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Message parsing
# ------------------------------------------------------------------------------


class InvalidArgsError(Exception):
    pass


class PositionalArg:
    def __init__(
        self,
        name: str,
        *,
        parse_name: bool = False,
        nargs: Union[int, str] = 1,
        default: Any = None,
        choices: Optional[Iterable[Any]] = None,
        type: Optional[Callable] = None,
        validate: Optional[Callable] = None,
    ):
        if (isinstance(nargs, int) and nargs < 1) and nargs not in ["?", "*", "+"]:
            raise ValueError(f"Bad nargs value {nargs!r}")
        self.name = name
        self.parse_name = parse_name
        self.nargs = nargs
        if default is None and nargs not in [1, "?"]:
            self.default = []
        else:
            self.default = default
        self._choices = choices
        self._type = type
        self._validate = validate

    def convert(self, value):
        if self._type is not None:
            return self._type(value)
        return value

    def validate(self, value):
        if self._choices is not None and value not in self._choices:
            return False
        if self._validate:
            return self._validate(value)
        return True


class ArgParser(argparse.ArgumentParser):
    """
    A specialised arg parser.

    The list of args to be parsed can contain the following, with no overlap:
     - Ordered positional args at the start
     - Regular argparse args with no order

    Positional args are added with 'add_positional_arg()'. The order of calls to
    this method determines the order the args must appear in. The following
    options are accepted:
     - parse_name: Whether the arg name should be parsed.
     - nargs: The number of args to accept. Accepted values are positive
        integers, "?" for 0 or 1, "*" for 0 or more, "+" for 1 or more.
     - choices: As for 'add_argument()'.
     - type: As for 'add_argument()'.

    Positional args are greedily consumed, but if an arg does not satisfy
    choices or if the 'type' callable raises an exception then no more values
    will be accepted for that arg.

    Examples:
     - If a positional arg has no type/choices restrictions and unbounded
        'nargs' (i.e. set to "*" or "+") then all positional options will be
        consumed by this arg.
     - If a positional arg has unbounded 'nargs' but has a 'type' that raises an
        exception for invalid args, subsequent args will take over the matching.
        Note that if insufficient options are matched (e.g. nargs="+" and no
        options are matched) then parsing ends with a standard error.

    Positional argument parsing ends as soon as an option starting with a dash
    is encountered, or when the positional args are exhausted. The remaining
    options are passed to a standard argparse parser to match args added with
    'add_argument()'.
    """

    def __init__(self):
        super().__init__(add_help=False)
        self._name_parse_args = []
        self._positional_args = []

    def parse_known_args(self, args: Iterable[str], namespace=None):
        """
        Override the default behaviour.
        """
        if namespace is None:
            namespace = argparse.Namespace()

        # Start with positional args.
        args = self._parse_positional_args(args, namespace)

        # Replace optional args so that they don't require the dashes.
        for i, arg in enumerate(args):
            if arg in self._name_parse_args:
                args[i] = f"--{arg}"

        # Regular parsing of remaining args
        return super().parse_known_args(args, namespace)

    def add_argument(self, name, *args, **kwargs):
        """
        Override the default behaviour.
        """
        if not name.startswith("--"):
            self._name_parse_args.append(name)
            name = "--" + name.lstrip("-")
        super().add_argument(name, *args, **kwargs)

    def error(self, message):
        raise InvalidArgsError(message)

    def add_positional_arg(self, name: str, **kwargs) -> None:
        """
        Add a positional argument for parsing.

        :param name:
            The name of the argument - must be unique.
        :param kwargs:
            Arguments to pass to the 'PositionalArg' class.
        """
        self._positional_args.append(PositionalArg(name, **kwargs))

    def _parse_positional_args(self, kws: Iterable[str], namespace) -> Iterable[str]:
        """
        Parse the positional args.

        :param kws:
            The provided keywords.
        :param namespace:
            The namespace to set argument values in.
        :return:
            The remaining unmatched keywords.
        """
        for arg in self._positional_args:
            result, kws = self._parse_single_positional_arg(arg, kws)
            setattr(namespace, arg.name, result)
        return kws

    def _parse_single_positional_arg(
        self, arg: PositionalArg, kws: Iterable[str]
    ) -> Tuple[Any, Iterable[str]]:
        """
        Parse a single positional arg. Raise InvalidArgsError if not enough
        matching args are found.
        """
        required = arg.nargs not in ["?", "*"]
        if isinstance(arg.nargs, int):
            max_matches = arg.nargs
            exp_args_string = str(arg.nargs)
        elif arg.nargs == "?":
            max_matches = 1
            exp_args_string = "optionally one"
        elif arg.nargs == "*":
            max_matches = None
            exp_args_string = "any number of"
        elif arg.nargs == "+":
            max_matches = None
            exp_args_string = "at least one"
        else:
            assert False

        # First parse the arg name if required.
        if kws and arg.parse_name:
            if kws[0] == arg.name:  # Found arg
                kws.pop(0)
            elif not required:  # No match
                return arg.default, kws
            else:
                raise InvalidArgsError(f"Expected to find {arg.name!r}")

        # Now parse argument values.
        matches = []
        while kws and (max_matches is None or len(matches) < max_matches):
            try:
                kw_value = arg.convert(kws[0])
                assert arg.validate(kw_value)
            except Exception as e:
                logger.debug(e)
                if arg.parse_name and not matches:
                    # We parsed the name of the arg, so we expected to find
                    # at least one value...
                    raise InvalidArgsError(
                        f"Got name of positional arg {arg.name!r} but no values"
                    )
                else:
                    break
            else:
                matches.append(kw_value)
                kws.pop(0)

        if required and not matches:
            raise InvalidArgsError(f"Expected {exp_args_string} {arg.name!r} arg")
        elif isinstance(arg.nargs, int) and len(matches) != arg.nargs:
            assert len(matches) < arg.nargs
            raise InvalidArgsError(f"Expected {exp_args_string} {arg.name!r} arg")

        arg_value = arg.default
        if matches:
            if arg.nargs in [1, "?"]:
                assert len(matches) == 1
                arg_value = matches[0]
            else:
                arg_value = matches

        return arg_value, kws


class BotMsgParser(ArgParser):
    def add_difficulty_arg(self):
        self.add_positional_arg("difficulty", nargs="?", type=Difficulty.from_str)

    def add_rank_type_arg(self):
        def convert(arg) -> str:
            try:
                return Difficulty.from_str(arg).name.lower()
            except InvalidArgsError:
                raise  # TODO
                # if arg == "combined":
                #     return "combined"
                # elif arg == "official":
                #     return "official"
                # else:
                #     raise InvalidArgsError(f"Invalid rank type {arg!r}")

        self.add_positional_arg("rank_type", nargs="?", type=convert)

    def add_per_cell_arg(self):
        self.add_argument("per-cell", type=int, choices=[1, 2, 3])

    def add_drag_select_arg(self):
        def _arg_type(arg):
            if arg == "on":
                return True
            elif arg == "off":
                return False
            else:
                raise InvalidArgsError("Drag select should be one of {'on', 'off'}")

        self.add_argument("drag-select", type=_arg_type)


# ------------------------------------------------------------------------------
# Message handling
# ------------------------------------------------------------------------------


CommandMapping = Dict[Optional[str], Union[Callable, "CommandMapping"]]


class RoomType(enum.Enum):
    GROUP = "group"
    DIRECT = "direct"

    def to_cmds(self) -> CommandMapping:
        if self is self.GROUP:
            return _GROUP_COMMANDS
        else:
            assert self is self.DIRECT
            return _DIRECT_COMMANDS


GENERAL_INFO = """\
Welcome to the Minegauler bot!

Instructions for downloading Minegauler can be found in the \
[GitHub repo](https://github.com/LewisGaul/minegauler/blob/master/README.md).

The bot provides the ability to check highscores and matchups for games of \
Minegauler, and also gives notifications whenever anyone in the group sets a \
new highscore.

There are a few settings to filter Minegauler games with:
 - difficulty: One of 'beginner', 'intermediate', 'expert' or 'master'.  
   By default the combination of beginner, intermediate and expert is used, \
   with 1000 used for any difficulties not completed.
 - drag-select: One of 'on' or 'off'.  
   By default no filter is applied (the best time of either mode is used).
 - per-cell: One of 1, 2 or 3.  
   By default no filter is applied (the best time of any mode is used).

All highscores are independent of each of the above modes, and all commands \
accept these filters to view specific times. E.g. 'ranks beginner per-cell 1'.

Commands can be issued in group chat and direct chat. Most of the commands are \
the same, however some are only available in one of the other (e.g. \
'set nickname'). Type 'help' or '?' to check the available commands.

To interact with a bot in Webex Teams group chats, the bot must be tagged. To \
do this, type @ followed by the bot's name. The client should auto-suggest a \
completion, at which point you'll need to press enter or tab to select the \
completion and turn it into a tag.

Some useful common commands:  
'ranks' - display rankings  
'matchups <name> <name> ...' - display comparison of times between users

Some useful group-chat commands:  
'challenge <name> ...' - challenge other users to a game

Some useful direct-chat commands:  
'set nickname' - set your nickname that you use in the Minegauler app
"""


def helpstring(text):
    def decorator(func):
        func.__helpstring__ = text
        return func

    return decorator


def schema(text):
    def decorator(func):
        func.__schema__ = text
        return func

    return decorator


def cmd_help(
    func: Callable, *, only_schema: bool = False, allow_markdown: bool = False
) -> str:
    lines = []
    if not only_schema:
        try:
            lines.append(func.__helpstring__)
        except AttributeError:
            logger.warning(
                "No helpstring found on message handling function %r", func.__name__
            )
    try:
        schema = func.__schema__
    except AttributeError:
        logger.warning("No schema found on message handling function %r", func.__name__)
    else:
        if allow_markdown:
            lines.append(f"`{schema}`")
        else:
            lines.append(schema)

    if not lines:
        return "Unexpected error: unable to get help message\n\n"

    return "\n\n".join(lines)


@helpstring("Get help for a command")
@schema("help [<command>]")
def group_help(args, **kwargs):
    allow_markdown = kwargs.get("allow_markdown", False)

    linebreak = "\n\n" if allow_markdown else "\n"
    commands = _flatten_cmds(_GROUP_COMMANDS)
    if allow_markdown:
        commands = f"`{commands}`"

    if not args:
        return commands

    func, _ = _map_to_cmd(" ".join(args), _GROUP_COMMANDS)
    if func is None:
        raise InvalidArgsError(linebreak.join(["Unrecognised command", commands]))
    else:
        return cmd_help(func, allow_markdown=allow_markdown)


@helpstring("Get help for a command")
@schema("help [<command>]")
def direct_help(args, **kwargs):
    allow_markdown = kwargs.get("allow_markdown", False)

    linebreak = "\n\n" if allow_markdown else "\n"
    commands = _flatten_cmds(_DIRECT_COMMANDS)
    if allow_markdown:
        commands = f"`{commands}`"

    if not args:
        return commands

    func, _ = _map_to_cmd(" ".join(args), _DIRECT_COMMANDS)
    if func is None:
        raise InvalidArgsError(linebreak.join(["Unrecognised command", commands]))
    else:
        return cmd_help(func, allow_markdown=allow_markdown)


@helpstring("Get information about the game")
@schema("info")
def info(args, **kwargs):
    # Check no args given.
    BotMsgParser().parse_args(args)
    return GENERAL_INFO


@helpstring("Get player info")
@schema(
    "player <name> [b[eginner] | i[ntermediate] | e[xpert] | m[aster]] "
    "[drag-select {on | off}] [per-cell {1 | 2 | 3}]"
)
def player(args, username: str, allow_markdown=False, **kwargs):
    parser = BotMsgParser()
    parser.add_positional_arg("username", choices=list(utils.USER_NAMES) + ["me"])
    parser.add_difficulty_arg()
    parser.add_per_cell_arg()
    parser.add_drag_select_arg()
    args = parser.parse_args(args)
    if args.username == "me":
        args.username = username

    highscores = utils.get_highscores(
        name=utils.USER_NAMES[args.username],
        difficulty=args.difficulty,
        drag_select=args.drag_select,
        per_cell=args.per_cell,
    )

    filters_str = formatter.format_filters(
        None, args.drag_select, args.per_cell, no_difficulty=True
    )
    if filters_str:
        filters_str = " with " + filters_str
    lines = [
        "Player info for {} ({}){}:".format(
            args.username, utils.USER_NAMES[args.username], filters_str
        )
    ]
    lines.extend(
        formatter.format_player_highscores(list(highscores), difficulty=args.difficulty)
    )

    linebreak = "  \n" if allow_markdown else "\n"

    return linebreak.join(lines)


@helpstring("Get rankings")
@schema(
    "ranks [b[eginner] | i[ntermediate] | e[xpert] | m[aster]] "
    "[drag-select {on | off}] [per-cell {1 | 2 | 3}]"
)
def ranks(args, **kwargs) -> str:
    allow_markdown = kwargs.get("allow_markdown", False)

    parser = BotMsgParser()
    parser.add_rank_type_arg()
    parser.add_per_cell_arg()
    parser.add_drag_select_arg()
    args = parser.parse_args(args)

    diff = Difficulty.from_str(args.rank_type) if args.rank_type else None
    times = utils.get_highscore_times(diff, args.drag_select, args.per_cell)

    lines = [
        "Rankings for {}".format(
            formatter.format_filters(args.rank_type, args.drag_select, args.per_cell)
        )
    ]
    ranks = formatter.format_highscore_times(times)
    if allow_markdown:
        ranks = f"```\n{ranks}\n```"
    lines.append(ranks)

    return "\n".join(lines)


@helpstring("Get stats for played games")
@schema(  # @@@ This is bad because it requires knowledge of sub-commands.
    "stats [players ...] [b[eginner] | i[ntermediate] | e[xpert] | m[aster]] "
    "[drag-select {on | off}] [per-cell {1 | 2 | 3}]"
)
def stats(args, **kwargs):
    parser = BotMsgParser()
    parser.add_difficulty_arg()
    parser.add_per_cell_arg()
    parser.add_drag_select_arg()
    args = parser.parse_args(args)
    return "Stats"


@helpstring("Get player stats")
@schema("stats players {all | <name> [<name> ...]}")
def stats_players(args, username: str, allow_markdown=False, **kwargs):
    parser = BotMsgParser()
    parser.add_positional_arg(
        "username", nargs="+", choices=list(utils.USER_NAMES) + ["me", "all"]
    )
    args = parser.parse_args(args)
    if "all" in args.username:
        if len(args.username) > 1:
            raise InvalidArgsError("'all' should be specified without usernames")
        users = utils.USER_NAMES.keys()
    else:
        users = {u if u != "me" else username for u in args.username}

    player_info = [utils.get_player_info(u) for u in users]
    lines = [formatter.format_player_info(player_info)]
    if allow_markdown:
        lines = ["```", *lines, "```"]

    return "\n".join(lines)


@helpstring("Get matchups for given players")
@schema(
    "matchups <name> <name> [<name> ...] "
    "[b[eginner] | i[ntermediate] | e[xpert] | m[aster]] "
    "[drag-select {on | off}] [per-cell {1 | 2 | 3}]"
)
def matchups(
    args,
    username: str,
    allow_markdown: bool = False,
    room_type=RoomType.DIRECT,
    **kwargs,
):
    parser = BotMsgParser()
    parser.add_positional_arg(
        "username", nargs="+", choices=list(utils.USER_NAMES) + ["me"]
    )
    parser.add_difficulty_arg()
    parser.add_per_cell_arg()
    parser.add_drag_select_arg()
    args = parser.parse_args(args)
    users = {u if u != "me" else username for u in args.username}
    if len(users) < 2 or len(users) > 5:
        raise InvalidArgsError("Require between 2 and 5 username args")
    names = {utils.USER_NAMES[u] for u in users}

    times = utils.get_highscore_times(
        args.difficulty, args.drag_select, args.per_cell, names
    )
    matchups = utils.get_matchups(times)

    if allow_markdown and room_type is RoomType.GROUP:
        users_str = ", ".join(utils.tag_user(u) for u in users)
    else:
        users_str = ", ".join(users)
    lines = [
        "Matchups between {} for {}:".format(
            users_str,
            formatter.format_filters(args.difficulty, args.drag_select, args.per_cell),
        )
    ]
    lines.extend(formatter.format_matchups(matchups))
    linebreak = "  \n" if allow_markdown else "\n"

    return linebreak.join(lines)


@helpstring("Get best matchups including at least one of specified players")
@schema(
    "best-matchups [<name> ...] "
    "[b[eginner] | i[ntermediate] | e[xpert] | m[aster]] "
    "[drag-select {on | off}] [per-cell {1 | 2 | 3}]"
)
def best_matchups(
    args, username: str, allow_markdown=False, room_type=RoomType.DIRECT, **kwargs
):
    parser = BotMsgParser()
    parser.add_positional_arg(
        "username", nargs="*", choices=list(utils.USER_NAMES) + ["me"]
    )
    parser.add_difficulty_arg()
    parser.add_per_cell_arg()
    parser.add_drag_select_arg()
    args = parser.parse_args(args)
    users = {u if u != "me" else username for u in args.username}
    names = {utils.USER_NAMES[u] for u in users}

    times = utils.get_highscore_times(
        args.difficulty, args.drag_select, args.per_cell, utils.USER_NAMES.values()
    )
    matchups = utils.get_matchups(times, include_users=names)[:10]

    if allow_markdown and room_type is RoomType.GROUP:
        users_str = ", ".join(utils.tag_user(u) for u in users)
    else:
        users_str = ", ".join(users)
    if users_str:
        users_str = " including " + users_str
    lines = [
        "Best matchups{} for {}:".format(
            users_str,
            formatter.format_filters(args.difficulty, args.drag_select, args.per_cell),
        )
    ]
    lines.extend(formatter.format_matchups(matchups))
    linebreak = "  \n" if allow_markdown else "\n"

    return linebreak.join(lines)


@helpstring("Challenge other players to a game")
@schema(
    "challenge <name> [<name> ...] "
    "[b[eginner] | i[ntermediate] | e[xpert] | m[aster]] "
    "[drag-select {on | off}] [per-cell {1 | 2 | 3}]"
)
def challenge(args, username: str, **kwargs):
    parser = BotMsgParser()
    parser.add_positional_arg(
        "username",
        nargs="+",
        choices=set(utils.USER_NAMES) - {username} - utils.NO_TAG_USERS,
    )
    parser.add_difficulty_arg()
    parser.add_per_cell_arg()
    parser.add_drag_select_arg()
    args = parser.parse_args(args)
    names = {u for u in args.username}

    users_str = ", ".join(utils.tag_user(u) for u in names)
    diff_str = args.difficulty + " " if args.difficulty else ""
    opts = dict()
    if args.drag_select:
        opts["drag-select"] = "on" if args.drag_select else "off"
    if args.per_cell:
        opts["per-cell"] = args.per_cell
    if opts:
        opts_str = " with {}".format(formatter.format_kwargs(opts))
    else:
        opts_str = ""

    return "{} has challenged {} to a {}game of Minegauler{}".format(
        username, users_str, diff_str, opts_str
    )


@helpstring("Set your nickname")
@schema("set nickname <name>")
def set_nickname(args, username: str, **kwargs):
    new = " ".join(args)
    if len(new) > 10:
        raise InvalidArgsError("Nickname must be no longer than 10 characters")
    for other in utils.USER_NAMES.values():
        if new.lower() == other.lower():
            raise InvalidArgsError(f"Nickname {other!r} already in use")
    if new.lower() in utils.USER_NAMES.keys() and new != username:
        raise InvalidArgsError(f"Cannot set nickname to someone else's username!")
    old = utils.USER_NAMES[username]
    logger.debug("Changing nickname of %s from %r to %r", username, old, new)
    utils.set_user_nickname(username, new)
    return f"Nickname changed from '{old}' to '{new}'"


# fmt: off
_COMMON_COMMANDS = {
    "help": None,
    "player": player,
    "ranks": ranks,
    "stats": {
        # None: stats,
        "players": stats_players,
    },
    "matchups": matchups,
    "best-matchups": best_matchups,
}

_GROUP_COMMANDS = {
    **_COMMON_COMMANDS,
    "help": group_help,
    "challenge": challenge,
}

_DIRECT_COMMANDS = {
    **_COMMON_COMMANDS,
    "help": direct_help,
    "info": info,
    "set": {
        "nickname": set_nickname,
    },
}
# fmt: on


def _map_to_cmd(msg: str, cmds: CommandMapping) -> Tuple[Callable, List[str]]:
    func = None
    words = msg.split()

    while words:
        next_word = words[0]
        if next_word in cmds:
            words.pop(0)
            if callable(cmds[next_word]):
                func = cmds[next_word]
                break
            else:
                cmds = cmds[next_word]
        else:
            break
        if None in cmds:
            func = cmds[None]

    return func, words


def _flatten_cmds(cmds: CommandMapping, root: bool = True) -> str:
    to_join = []
    for k, v in cmds.items():
        item = k
        if isinstance(v, dict):
            item += " " + _flatten_cmds(v, root=False)
        if item:
            to_join.append(item)
    ret = " | ".join(to_join)
    if None in cmds:
        ret = f"[{ret}]"
    elif len(cmds) > 1 and not root:
        ret = f"{{{ret}}}"
    return ret


def parse_msg(
    msg: str, room_type: RoomType, *, allow_markdown: bool = False, **kwargs
) -> str:
    """
    Parse a message and perform the corresponding action.

    :param msg:
        The message to parse.
    :param room_type:
        The room type the message was received in.
    :param allow_markdown:
        Whether to allow markdown in the response.
    :param kwargs:
        Other arguments to pass on to sub-command functions.
    :return:
        Response text.
    :raise InvalidArgsError:
        Unrecognised command. The text of the error is a suitable error/help
        message.
    """
    msg = msg.strip()
    if msg.endswith("?") and not (msg.startswith("help ") and msg.split()[1] != "?"):
        # Change "?" at the end to be treated as help, except for the case where
        # this is a double help intended for a subcommand, e.g.
        # 'help matchups ?'.
        msg = "help " + msg[:-1]

    cmds = room_type.to_cmds()
    func = None
    try:
        func, args = _map_to_cmd(msg, cmds)
        if func is None:
            raise InvalidArgsError("Base command not found")
        return func(args, allow_markdown=allow_markdown, room_type=room_type, **kwargs)
    except InvalidArgsError as e:
        logger.debug("Invalid message: %r", msg)
        if func is None:
            raise InvalidArgsError(
                "Unrecognised command - try 'help' or 'info' in direct chat"
            )
        else:
            linebreak = "\n\n" if allow_markdown else "\n"
            resp_msg = cmd_help(func, only_schema=True, allow_markdown=allow_markdown)
            resp_msg = linebreak.join([f"Unrecognised command: {str(e)}", resp_msg])

        raise InvalidArgsError(resp_msg) from e


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------


def main(argv):
    utils.read_users_file()
    try:
        # TODO: Need to not join argv, since player names can contain spaces.
        resp = parse_msg(" ".join(argv), RoomType.DIRECT, username="dummy-user")
    except InvalidArgsError as e:
        resp = str(e)
    print(resp)


if __name__ == "__main__":
    main(sys.argv[1:])
