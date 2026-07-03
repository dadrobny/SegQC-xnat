@echo off
REM Thin wrapper -> the usage-gated AIDE loop supervisor. Config: loop.local.toml.
python "%~dp0loop.py" %*
