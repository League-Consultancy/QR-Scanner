@echo off

:: Check if virtual environment exists
if not exist .venv (
    echo Error: Virtual environment (.venv) not found. Please run setup-windows.bat first. >&2
    exit /b 1
)

:: Activate the virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

:: Run app.py
echo Running app.py...
python app.py
