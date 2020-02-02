"""
utils.py - General test utils

February 2020, Lewis Gaul
"""

__all__ = ("activate_patches",)

import contextlib
from typing import Iterable
from unittest import mock


@contextlib.contextmanager
def activate_patches(patches: Iterable[mock._patch]):
    """
    Context manager to activate multiple mock patches.

    :param patches:
        Patches to start and stop.
    """
    mocks = []
    for patch in patches:
        mocks.append(patch.start())
    try:
        yield tuple(mocks)
    finally:
        for patch in patches:
            patch.stop()
