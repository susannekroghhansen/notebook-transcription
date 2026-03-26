#!/bin/bash

echo ""
echo "Stopping Notebook App on port 8000..."

# Find and kill any process using port 8000
PID=$(lsof -ti :8000)

if [ -n "$PID" ]; then
    kill $PID
    echo "App stopped (killed PID $PID)."
else
    echo "No app found running on port 8000."
fi

echo ""
