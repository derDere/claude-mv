# claude-mv launcher (PowerShell) — pulls the tool from GitHub via uvx and runs it.
# Drop this file into any PATH directory and you can call `claude-mv ...` from PowerShell.
# Note: PowerShell may block unsigned scripts. If so, run once as admin:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
& uvx --from git+https://github.com/derDere/claude-mv.git claude-mv @args
exit $LASTEXITCODE
