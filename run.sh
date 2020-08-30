#!/usr/bin/env bash

if [[ -f .venv/bin/python ]]; then
  PYTHON_EXE=.venv/bin/python
else
  PYTHON_EXE=python3
fi

PYTHONPATH='bootstrap' "$PYTHON_EXE" -m cli "$@"
