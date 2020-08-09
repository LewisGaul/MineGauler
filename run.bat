@echo off

IF EXIST .venv\Scripts\python.exe (
  set PYTHON_EXE=.venv\Scripts\python.exe
) ELSE (
  set PYTHON_EXE=python
)

cmd /C "set PYTHONPATH=bootstrap && %PYTHON_EXE% -m cli %*"
