#!/bin/sh
set -e

ENV_EXAMPLE="docker/.env.example"
ENV_DEV="docker/.env.dev"

echo ""
echo "Setting up environment..."
echo "========================="

if [ ! -f "$ENV_EXAMPLE" ]; then
    echo "Error: $ENV_EXAMPLE not found. Are you running from the repo root?"
    exit 1
fi

if [ -f "$ENV_DEV" ]; then
    printf "  %s already exists. Overwrite? [y/N] " "$ENV_DEV"
    read -r answer
    case "$answer" in
        [yY]*)
            cp "$ENV_EXAMPLE" "$ENV_DEV"
            echo "  Overwritten."
            ;;
        *)
            echo "  Kept existing $ENV_DEV."
            ;;
    esac
else
    cp "$ENV_EXAMPLE" "$ENV_DEV"
    echo "  Created $ENV_DEV from $ENV_EXAMPLE."
fi

echo ""
echo "  Review docker/.env.dev and adjust values if needed before running 'make fireform'."
echo ""
