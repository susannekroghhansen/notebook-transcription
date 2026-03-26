#!/bin/bash

# Navigate to the notebook-webapp folder
cd "$(dirname "$0")"

# Load ANTHROPIC_API_KEY from ~/.zshrc if not already set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    export ANTHROPIC_API_KEY=$(grep -oP 'export ANTHROPIC_API_KEY=["'"'"']?\K[^"'"'"'\s]+' ~/.zshrc 2>/dev/null | head -1)
fi

nohup python3 menubar.py &> /tmp/notebook-menubar.log &
