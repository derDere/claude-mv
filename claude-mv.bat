@echo off
REM claude-mv launcher (cmd.exe) — pulls the tool from GitHub via uvx and runs it.
REM Drop this file into any PATH directory and you can call `claude-mv ...` from cmd.
uvx --from "git+https://github.com/derDere/claude-mv.git" claude-mv %*
