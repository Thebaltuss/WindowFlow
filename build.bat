@echo off
setlocal
cd /d "%~dp0"

set "BUILD_PYTHON=.venv\Scripts\python.exe"
set "BUILD_PYINSTALLER=.venv\Scripts\pyinstaller.exe"

if exist ".buildenv\Scripts\python.exe" (
    set "BUILD_PYTHON=.buildenv\Scripts\python.exe"
    set "BUILD_PYINSTALLER=.buildenv\Scripts\pyinstaller.exe"
)

if not exist "%BUILD_PYTHON%" (
    echo Create the virtual environment first with start.bat.
    pause
    exit /b 1
)

if "%BUILD_PYTHON%"==".venv\Scripts\python.exe" (
    "%BUILD_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Dependency installation failed.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -c "from PIL import Image; Image.open('icon.png').convert('RGBA').save('icon.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if errorlevel 1 (
    echo Could not create icon.ico from icon.png.
    pause
    exit /b 1
)

"%BUILD_PYINSTALLER%" --noconfirm --clean windowflow.spec
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo Build complete: dist\WindowFlow.exe
exit /b 0
