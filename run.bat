@echo off
REM Start the Nexus Ops Grid UI on http://localhost:8501
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\python -m pip install -r requirements.txt
)
if not exist ".env" (
    copy .env.example .env >nul
    echo Created .env from .env.example - fill in your credentials when ready.
)
.venv\Scripts\python -m streamlit run app.py
