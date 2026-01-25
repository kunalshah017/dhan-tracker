#!/bin/bash
# Development script to run both FastAPI and Vite dev servers side by side
# Both logs are visible in the terminal with color-coded prefixes

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Dhan Tracker Development Server${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down servers...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

# Trap Ctrl+C and cleanup
trap cleanup SIGINT SIGTERM

# Check if we're in the right directory
if [ ! -f "server.py" ]; then
    echo -e "${RED}Error: server.py not found. Run this script from the project root.${NC}"
    exit 1
fi

if [ ! -d "frontend" ]; then
    echo -e "${RED}Error: frontend directory not found.${NC}"
    exit 1
fi

# Start FastAPI server
echo -e "${BLUE}[Backend]${NC} Starting FastAPI server on http://localhost:8000"
uvicorn server:app --reload --host 0.0.0.0 --port 8000 2>&1 | sed "s/^/$(printf "${BLUE}[Backend]${NC} ")/" &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 2

# Start Vite dev server
echo -e "${GREEN}[Frontend]${NC} Starting Vite dev server on http://localhost:5173"
cd frontend && npm run dev 2>&1 | sed "s/^/$(printf "${GREEN}[Frontend]${NC} ")/" &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}   Servers are running!${NC}"
echo -e "${YELLOW}   Frontend: http://localhost:5173${NC}"
echo -e "${YELLOW}   Backend:  http://localhost:8000${NC}"
echo -e "${YELLOW}   Press Ctrl+C to stop both servers${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""

# Wait for both processes
wait
