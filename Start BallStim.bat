@echo off
title BallStim
cd /d "%~dp0"
set "PSYPY="
if exist "%ProgramFiles%\PsychoPy\python.exe" set "PSYPY=%ProgramFiles%\PsychoPy\python.exe"
if not defined PSYPY if exist "%ProgramFiles%\PsychoPy3\python.exe" set "PSYPY=%ProgramFiles%\PsychoPy3\python.exe"
if not defined PSYPY if exist "%LocalAppData%\Programs\PsychoPy\python.exe" set "PSYPY=%LocalAppData%\Programs\PsychoPy\python.exe"
if not defined PSYPY (
    echo Could not find PsychoPy on this computer.
    echo Open app\ballstim.py in the PsychoPy Coder and press Run instead.
    pause
    exit /b 1
)
echo Starting BallStim with "%PSYPY%" ...
"%PSYPY%" "app\ballstim.py"
if errorlevel 1 pause
