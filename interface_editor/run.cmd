@echo off
if exist "%~dp0.venv\Scripts\python.exe" if exist "%~dp0app\_interface_core*.pyd" goto source
if exist "%~dp0dist\windows\Start.cmd" (
    call "%~dp0dist\windows\Start.cmd" %*
    exit /b
)
echo Run build.ps1 first, or use the portable dist\windows package.
pause
exit /b 1
:source
"%~dp0.venv\Scripts\python.exe" "%~dp0app\main.py" %*
if errorlevel 1 pause
