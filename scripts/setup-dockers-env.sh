#!/bin/bash

source venv/bin/activate
if command -v uv > /dev/null 2>&1; then
    uv pip install -r requirements.txt
else
    pip install -r requirements.txt
fi
