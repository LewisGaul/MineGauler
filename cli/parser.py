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


class Arg:
    """Schema arg."""

    def __init__(
        self,
        *,
        name: str,
        help_: str,
        command: Optional[str] = None,
        positional: bool = False,
        type_: typing.Type = str,
        enum: Optional[List] = None,
        default: Optional = None,
    ):
        self.name = name
        self.help = help_
        self.command = command
        self.positional = positional
        self.type = type_
        self.enum = enum
        self.default = default

    @classmethod
    def from_dict(cls, data: Dict[str, typing.Any]) -> "Arg":
        kwargs = data.copy()
        kwargs["help_"] = kwargs.pop("help")
        kwargs["type_"] = cls._process_type_field(kwargs.pop("type", "string"))
        return cls(**kwargs)

    @staticmethod
    def _process_type_field(value: str) -> typing.Type:
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
        return value


class _NodeBase:
    """Base class for nodes."""

    def __init__(
        self,
        *,
        keyword: Optional[str] = None,
        help_: str,
        command: Optional[str] = None,
        args: Optional[List[Arg]] = None,
        subtree: Optional[List["_NodeBase"]] = None,
    ):
        self.keyword = keyword
        self.help = help_
        self.command = command
        self.args = args if args else []
        self.subtree = subtree if subtree else []
        self.parent = None  # type: Optional[_NodeBase]
        for x in subtree:
            x.parent = self

    @classmethod
    def from_dict(cls, data: Dict[str, typing.Any]) -> "_NodeBase":
        kwargs = data.copy()
        kwargs["help_"] = kwargs.pop("help")
        kwargs["args"] = cls._process_args_field(kwargs.pop("args", []))
        kwargs["subtree"] = cls._process_subtree_field(kwargs.pop("subtree", []))
        return cls(**kwargs)

    @staticmethod
    def _process_subtree_field(value: List[Dict[str, typing.Any]]) -> List["_NodeBase"]:
        return [SubNode.from_dict(x) for x in value]

    @staticmethod
    def _process_args_field(value: List[Dict[str, typing.Any]]) -> List[Arg]:
        return [Arg.from_dict(x) for x in value]


class RootNode(_NodeBase):
    """Root schema node."""

    def __init__(self, **kwargs):
        if "keyword" in kwargs:
            raise TypeError("__init__() got an unexpected keyword argument 'keyword'")
        super().__init__(**kwargs)

    def __repr__(self):
        return "<RootNode>"


class SubNode(_NodeBase):
    """Sub schema node."""

    def __init__(self, *, keyword: str, **kwargs):
        kwargs["keyword"] = keyword
        super().__init__(**kwargs)

    def __repr__(self):
        keywords = []
        node = self
        while node.keyword:
            keywords.insert(0, node.keyword)
            node = node.parent
        return "<SubNode({})>".format(".".join(keywords))


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
        self._schema = RootNode.from_dict(schema)
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
        if node.subtree:
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
