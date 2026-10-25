@echo off
cd /d "%~dp0"
set PATH=%~dp0build;C:\msys64\ucrt64\bin;%PATH%
rem prefer the release exe: no console, log -> build\rel\savagewind.log (a console app's stats line
rem writing to a console or pipe stalled the game thread ~180ms every 2s - the "hitch every few seconds")
if exist build\rel\savagewind.exe (
    start "" build\rel\savagewind.exe
) else (
    start "" cmd /c "build\savagewind.exe >nul 2>&1"
)
