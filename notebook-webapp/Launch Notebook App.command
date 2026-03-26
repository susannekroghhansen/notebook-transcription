#!/bin/bash

# Navigate to the notebook-webapp folder
cd "$(dirname "$0")"

# Start the uvicorn server in the background
uvicorn main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

# Wait for the server to start
sleep 2

# Open the app in the default browser
open http://localhost:8000

echo ""
echo "=========================================="
echo "  Notebook App is running!"
echo "  URL: http://localhost:8000"
echo ""
echo "  To stop the app, close this window."
echo "=========================================="
echo ""

# Keep the terminal open and wait for the server process
wait $SERVER_PID
