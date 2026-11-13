@echo off
where py >nul 2>nul && (py -3 "%~dp0pypimgr.py" %* & exit /b %errorlevel%)
python "%~dp0pypimgr.py" %*
