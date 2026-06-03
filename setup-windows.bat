@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   ScanMatrix Setup for Windows
echo ========================================

:: 1. Install uv if not available
where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo 🔧 uv is not installed. Installing uv...
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if %ERRORLEVEL% neq 0 (
        echo Error: Failed to install uv. >&2
        exit /b 1
    fi
    
    :: Add uv to PATH for the rest of this script
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    
    :: Confirm uv installation
    where uv >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo Error: uv installation succeeded but 'uv' command is still not found in PATH. >&2
        exit /b 1
    fi
) else (
    echo ✔ uv is already installed.
)

:: Show uv version
uv --version

:: 2. Install Python 3.12.13 using uv
echo Installing Python 3.12.13 using uv...
uv python install 3.12.13
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to install Python 3.12.13. >&2
    exit /b 1
)

:: 3. Create virtual environment (.venv) using Python 3.12.13
echo Creating virtual environment (.venv) using Python 3.12.13...
uv venv .venv --python 3.12.13
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to create virtual environment. >&2
    exit /b 1
)

:: 4. Install all requirements
if exist requirements.txt (
    echo Installing requirements from requirements.txt...
    uv pip install --python .venv -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo Error: Failed to install requirements. >&2
        exit /b 1
    fi
    echo ✔ Requirements installed successfully.
) else (
    echo ⚠ requirements.txt not found! Skipping packages installation.
)

echo === Setup Completed Successfully ===
echo To Run the Software, run: run-windows.bat
