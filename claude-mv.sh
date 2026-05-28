#!/usr/bin/env bash
# claude-mv launcher — pulls the tool from GitHub via uvx and runs it.
# Drop this file into a PATH directory (e.g. /usr/local/bin or ~/.local/bin),
# make it executable (chmod +x), and you can call `claude-mv …` anywhere.
exec uvx -q --from git+https://github.com/derDere/claude-mv.git claude-mv "$@"
