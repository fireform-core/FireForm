#!/bin/bash
cat << 'EOF'
    ______                ______                     
   / ____/(_)_______     / ____/___  _________ ___ 
  / /_   / // ___/ _ \  / /_  / __ \/ ___/ __ `__ \
 / __/  / // /  /  __/ / __/ / /_/ / /  / / / / / /
/_/    /_//_/   \___/ /_/    \____/_/  /_/ /_/ /_/ 
EOF
echo "Make sure to have docker installed"
echo "Building containers..."
echo "============================================"
make build
echo "============================================"
echo "Starting containers..."
echo "============================================"
make up
echo "============================================"
echo "Use make down to stop" 
echo "Use docker ps to verify, you should see 3 containers:"
echo "\t* fireform-app"
echo "\t* fireform-frontend"
echo "\t* ollama/ollama:latest"
docker ps
echo "============================================"
echo "Pulling mistral from ollama"
echo "============================================"
make pull-model
echo "============================================"
echo "Done"
