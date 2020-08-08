# August 2020, Lewis Gaul

"""
CLI parsing.

"""

import argparse as argparse
import sys
import typing
from typing import Dict, List, Optional


# ------------------------------------------------------------------------------
# Yaml decomposition
# ------------------------------------------------------------------------------


class _CommonFieldsMixin:
    """Mixin to provide handling for common schema fields."""

    _help: str
    _command: Optional[str] = None

    @property
    def help(self) -> str:
        return self._help

    @help.setter
    def help(self, value: str):
        if type(value) is not str:
            raise ValueError("The help string is required")
        self._help = value

    @property
    def command(self) -> Optional[str]:
        return self._command

    @command.setter
    def command(self, value: Optional[str]):
        if value is not None and type(value) is not str:
            raise ValueError("Command should be a string if set")
        self._command = value


class Arg(_CommonFieldsMixin):
    """Schema arg."""

    _name: str
    _positional: bool = False
    _type: typing.Type = str
    _enum: Optional[List[str]] = None

    def __init__(self, obj: Dict[str, typing.Any]):
        required_fields = {"name", "help"}
        missing_fields = required_fields - set(obj)
        if missing_fields:
            raise ValueError("Missing fields: {}".format(", ".join(missing_fields)))
        for k, v in obj.items():
            setattr(self, k, v)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        if type(value) is not str:
            raise ValueError("Name is required and should be a string")
        self._name = value

    @property
    def positional(self) -> bool:
        return self._positional

    @positional.setter
    def positional(self, value: bool):
        if type(value) is not bool:
            raise ValueError("Positional should be a boolean")
        self._positional = value

    @property
    def type(self) -> typing.Type:
        return self._type

    @type.setter
    def type(self, value: str):
        # TODO: 'type' should be an enum rather than a Python type.
        accepted_types = {
            "integer": int,
            "string": str,
            "float": float,
            "flag": bool,
            "text": list,
        }
        if value in accepted_types:
            value = accepted_types[value]
        else:
            raise ValueError(
                "Unrecognised type {!r}, accepted types are: {}".format(
                    value, ", ".join(accepted_types)
                )
            )
        self._type = value


class _NodeBase(_CommonFieldsMixin):
    """Base class for nodes."""

    _keyword: Optional[str]
    _subtree: List["_NodeBase"]
    _args: List[Arg]
    parent: Optional["_NodeBase"]

    def __init__(self, obj: Dict[str, typing.Any]):
        required_fields = {"help"}
        missing_fields = required_fields - set(obj)
        if missing_fields:
            raise ValueError("Missing fields: {}".format(", ".join(missing_fields)))
        # Mutable defaults, initialised per-instance.
        self._subtree = []
        self._args = []
        for k, v in obj.items():
            setattr(self, k, v)

    @property
    def keyword(self) -> Optional[str]:
        return None

    @property
    def subtree(self) -> List["_NodeBase"]:
        return self._subtree

    @subtree.setter
    def subtree(self, value: List[Dict]):
        if type(value) is not list:
            raise ValueError("Subtree must be a list of nodes")
        self._subtree.clear()
        for x in value:
            node = SubNode(x)
            node.parent = self
            self._subtree.append(node)

    @property
    def args(self) -> List["Arg"]:
        return self._args

    @args.setter
    def args(self, value: List):
        if type(value) is not list:
            raise ValueError("Args must be a list of args")
        self._args = [Arg(x) for x in value]


class RootNode(_NodeBase):
    """Root schema node."""

    parent: None = None

    def __repr__(self):
        return "<RootNode>"


class SubNode(_NodeBase):
    """Sub schema node."""

    _keyword: str
    parent: _NodeBase

    def __init__(self, obj: Dict[str, typing.Any]):
        required_fields = {"help", "keyword"}
        missing_fields = required_fields - set(obj)
        if missing_fields:
            raise ValueError("Missing fields: {}".format(", ".join(missing_fields)))
        super().__init__(obj)

    def __repr__(self):
        keywords = []
        node = self
        while node.keyword:
            keywords.insert(0, node.keyword)
            node = node.parent
        return "<SubNode({})>".format(".".join(keywords))

    @property
    def keyword(self) -> str:
        return self._keyword

    @keyword.setter
    def keyword(self, value: str):
        if type(value) is not str:
            raise ValueError("Keyword is required and should be a string")
        self._keyword = value


# ------------------------------------------------------------------------------
# Argument parser
# ------------------------------------------------------------------------------


class CLIParser:
    """Argument parser based off a structured definition."""

    def __init__(self, schema: Dict[str, typing.Any], *, prog: Optional[str] = None):
        """
        :param schema:
            The schema for the arg parsing.
        """
        self._schema = RootNode(schema)
        self._prog = prog

    def parse_args(
        self, args: Optional[List[str]] = None, namespace=None
    ) -> argparse.Namespace:
        if args is None:
            args = sys.argv

        # Take a copy of the args.
        remaining_args = list(args)
        # Loop through the args until we find a non-keyword.
        node = self._schema
        consumed_args = []
        show_help = False
        while node.subtree and remaining_args:
            arg = remaining_args[0]
            if arg in ["-h", "--help"]:
                # TODO: Not sure how best to handle a 'help' arg:
                #   - Accept anywhere or only after the last given keyword
                #   - Treat as help for last given node, or for the node it
                #     appears directly after (break here instead of continue)
                #  Currently accepted anywhere and enacted on last given node.
                show_help = True
                remaining_args.pop(0)
                continue
            keywords = {x.keyword: x for x in node.subtree}
            if arg in keywords:
                consumed_args.append(remaining_args.pop(0))
                node = keywords[arg]
            else:
                break

        if show_help:
            remaining_args.insert(0, "--help")

        # Construct an arg parser for the node we reached.
        if self._prog:
            prog_args = [self._prog] + consumed_args
        else:
            prog_args = consumed_args
        parser = argparse.ArgumentParser(
            prog=" ".join(prog_args),
            description=node.help,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        # Use subparsers to represent the subnodes in displayed help.
        if node.subtree and show_help:
            subparsers = parser.add_subparsers(title="submodes")
            subparsers.required = node.command is None
            for subnode in node.subtree:
                subparsers.add_parser(subnode.keyword, help=subnode.help)
        # Add arguments for end-of-command.
        for arg in node.args:
            name = arg.name.replace("-", "_") if arg.positional else "--" + arg.name
            kwargs = dict()
            kwargs["help"] = arg.help
            if arg.type is bool:
                kwargs["action"] = "store_true"
            elif arg.type is list:
                kwargs["nargs"] = argparse.REMAINDER
            parser.add_argument(name, **kwargs)

        args_ns = parser.parse_args(remaining_args, namespace)
        args_ns.command = node.command
        args_ns.remaining_args = remaining_args
        return args_ns
