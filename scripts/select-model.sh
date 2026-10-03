#!/bin/sh
set -e

ENV_DEV="docker/.env.dev"
COMPOSE="docker compose -f docker/dev/compose.yml --env-file $ENV_DEV"

# model name | approx size
MODELS="qwen2.5:1.5b|~1GB qwen2.5:3b|~2GB qwen2.5:7b|~4GB llama3.2:3b|~2GB mistral:7b|~4GB"

current_model=""
if [ -f "$ENV_DEV" ]; then
    current_model=$(grep -E '^OLLAMA_MODEL=' "$ENV_DEV" | cut -d= -f2 | tr -d '[:space:]')
fi

echo ""
echo "Select Ollama model"
echo "==================="
[ -n "$current_model" ] && echo "  Current: $current_model"
echo ""

i=1
for entry in $MODELS; do
    name=$(echo "$entry" | cut -d'|' -f1)
    size=$(echo "$entry" | cut -d'|' -f2)
    if [ "$name" = "${current_model}" ]; then
        echo "  $i) $name  $size  [current]"
    else
        echo "  $i) $name  $size"
    fi
    i=$((i + 1))
done
echo "  $i) Enter custom model name"
i=$((i + 1))
echo "  $i) Keep current"
echo ""
printf "Choice [1-$i]: "
read -r choice

total=$(echo "$MODELS" | wc -w | tr -d '[:space:]')
keep_choice=$((total + 2))
custom_choice=$((total + 1))

if [ "$choice" = "$keep_choice" ] || [ -z "$choice" ]; then
    echo "  Keeping current model: ${current_model:-qwen2.5:1.5b}"
    echo ""
    exit 0
fi

if [ "$choice" = "$custom_choice" ]; then
    printf "  Enter model name (e.g. phi3:mini): "
    read -r selected
    if [ -z "$selected" ]; then
        echo "  No model entered. Keeping current."
        echo ""
        exit 0
    fi
    selected_size="unknown size"
else
    # Validate numeric choice in range
    if ! echo "$choice" | grep -qE '^[0-9]+$' || [ "$choice" -lt 1 ] || [ "$choice" -gt "$total" ]; then
        echo "  Invalid choice. Keeping current model."
        echo ""
        exit 0
    fi
    i=1
    for entry in $MODELS; do
        if [ "$i" = "$choice" ]; then
            selected=$(echo "$entry" | cut -d'|' -f1)
            selected_size=$(echo "$entry" | cut -d'|' -f2)
        fi
        i=$((i + 1))
    done
fi

# Patch OLLAMA_MODEL in .env.dev
tmp=$(mktemp)
sed "s|^OLLAMA_MODEL=.*|OLLAMA_MODEL=$selected|" "$ENV_DEV" > "$tmp"
mv "$tmp" "$ENV_DEV"
echo ""
echo "  OLLAMA_MODEL set to: $selected"

# If container is running, check and optionally pull immediately.
# If not running, the caller (make init) handles the pull prompt.
if $COMPOSE ps ollama 2>/dev/null | grep -q "running"; then
    if $COMPOSE exec -T ollama ollama list 2>/dev/null | grep -q "^$selected"; then
        echo "  Model already pulled. Nothing to download."
        echo ""
        exit 0
    fi

    echo ""
    printf "  Model not yet downloaded ($selected_size). Pull now? [y/N] "
    read -r pull_answer
    case "$pull_answer" in
        [yY]*)
            echo ""
            $COMPOSE exec -T ollama ollama pull "$selected"
            echo ""
            echo "  Model ready."
            ;;
        *)
            echo "  Skipped. Run 'make pull-model' when ready."
            ;;
    esac
fi

echo ""
