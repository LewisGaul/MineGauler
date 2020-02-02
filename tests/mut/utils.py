"""
utils.py - General test utils

December 2019, Lewis Gaul
"""

__all__ = ("make_true_mock",)

from unittest import mock


def make_true_mock(cls: type) -> type:
    """Mock a class without breaking type checking."""

    class _Tmp(cls):
        __name__ = f"Mock{cls.__name__}"

        def __init__(self, *args, **kwargs):
            self._mock = mock.MagicMock()
            # Qt insists that the superclass's __init__() method is called...
            super().__init__(*args, **kwargs)

        def __getattribute__(self, item):
            if item in ["_mock", "__init__"]:
                return super().__getattribute__(item)
            return getattr(self._mock, item)

        def __setattribute__(self, key, value):
            if key == "_mock":
                return super().__setattribute__(key, value)
            setattr(self._mock, key, value)

    return _Tmp
