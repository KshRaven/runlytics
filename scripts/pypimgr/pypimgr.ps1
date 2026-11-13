# Launcher: runs pypimgr.py with the same arguments.
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { & py -3 "$PSScriptRoot\pypimgr.py" @args } else { & python "$PSScriptRoot\pypimgr.py" @args }
exit $LASTEXITCODE
