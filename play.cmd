@echo off
cd /d "%~dp0"
set PATH=%~dp0build;C:\msys64\ucrt64\bin;%PATH%
start "" "build\savagewind.exe"
