@echo off
REM Development script to run both FastAPI and Vite dev servers side by side
REM For Windows Command Prompt

echo ========================================
echo    Dhan Tracker Development Server
echo ========================================
echo.

REM Check if we're in the right directory
if not exist "server.py" (
    echo Error: server.py not found. Run this script from the project root.
    exit /b 1
)

if not exist "frontend" (
    echo Error: frontend directory not found.
    exit /b 1
)

echo Starting FastAPI server on http://localhost:8000
echo Starting Vite dev server on http://localhost:5173
echo.
echo Press Ctrl+C in each window to stop the servers
echo.

REM Start backend in a new window
start "Dhan Tracker - Backend" cmd /k "uvicorn server:app --reload --host 0.0.0.0 --port 8000"

REM Start frontend in a new window
start "Dhan Tracker - Frontend" cmd /k "cd frontend && npm run dev"

echo Servers started in separate windows.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
