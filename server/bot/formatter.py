"""
formatter.py - Format bot messages

February 2020, Lewis Gaul
"""

__all__ = (
    "format_highscores",
    "format_highscore_times",
    "format_kwargs",
    "format_matchups",
    "format_player_highscores",
    "format_player_info",
)

import time
from typing import Iterable, List, Mapping, Optional, Tuple

import tabulate

from minegauler.shared import highscores as hs

from .utils import Matchup, PlayerInfo


tabulate.PRESERVE_WHITESPACE = True


def format_highscores(highscores: Iterable[hs.HighscoreStruct]) -> str:
    return format_highscore_times([(h.name, h.elapsed) for h in highscores])


def format_highscore_times(highscores: Iterable[Tuple[str, float]]) -> str:
    lines = [
        f"{i+1:2d}. {h[0][:10]:<10s}  {h[1]:7.2f}" for i, h in enumerate(highscores)
    ]
    return "\n".join(lines)


def format_player_highscores(
    highscores: List[hs.HighscoreStruct], difficulty: Optional[str] = None
) -> List[str]:
    lines = []
    if highscores:
        last_played = format_timestamp(max(h.timestamp for h in highscores))
    else:
        last_played = "<n/a>"
    lines.append(f"Last game played on {last_played}")

    if not difficulty:
        for diff in ["beginner", "intermediate", "expert", "master"]:
            hscores = [h.elapsed for h in highscores if h.difficulty.lower() == diff[0]]
            if hscores:
                best = f"{min(hscores):.2f}"
            else:
                best = "None"
            line = "{}: {}".format(diff.capitalize(), best)
            lines.append(line)
    else:
        lines.append(f"Top {difficulty} times:")
        for h in highscores[:5]:
            line = "{:.2f} ({:.2f} 3bv/s) - {}".format(
                h.elapsed, h.bbbvps, format_timestamp(h.timestamp)
            )
            lines.append(line)

    return lines


def format_player_info(players: Iterable[PlayerInfo]) -> str:
    headers = [
        "Username",
        "Nickname",
        "Combined time",
        "Modes played",
        "Last highscore",
    ]
    data = [
        (
            p.username,
            p.nickname[:10],
            p.combined_time,
            f"{p.types_played:2d}/24",
            format_timestamp(p.last_highscore) if p.last_highscore else "None",
        )
        for p in sorted(players, key=lambda x: x.combined_time)
    ]
    return tabulate.tabulate(
        data,
        headers=headers,
        tablefmt="presto",
        stralign="center",
        numalign="center",
        floatfmt="7.2f",
    )


def format_kwargs(kwargs: Mapping) -> str:
    return ", ".join(f"{k}={v}" for k, v in kwargs.items())


def format_filters(
    difficulty: Optional[str],
    drag_select: Optional[bool],
    per_cell: Optional[int],
    *,
    no_difficulty=False,
) -> str:
    opts = dict()
    if not no_difficulty:
        if not difficulty:
            difficulty = "combined"
        opts["difficulty"] = difficulty
    if drag_select is not None:
        opts["drag-select"] = "on" if drag_select else "off"
    if per_cell is not None:
        opts["per-cell"] = per_cell
    return format_kwargs(opts)


def format_matchups(matchups: Iterable[Matchup]) -> List[str]:
    return [
        "{} ({:.2f}) vs {} ({:.2f}) - {:.2f}% difference".format(*m) for m in matchups
    ]


def format_timestamp(timestamp: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
