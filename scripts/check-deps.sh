#!/bin/sh
set -e

PASS=0
FAIL=1
errors=0

check() {
    label="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo "  [ok] $label"
    else
        echo "  [!!] $label"
        errors=$((errors + 1))
    fi
}

echo ""
echo "Checking dependencies..."
echo "========================"

# Docker daemon running
check "Docker daemon is running" docker info

# docker compose v2 (plugin form, not legacy docker-compose)
check "docker compose v2 available" docker compose version

# Minimum Docker version: 24 (BuildKit cache mounts stable)
DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null | cut -d. -f1)
if [ -n "$DOCKER_VERSION" ] && [ "$DOCKER_VERSION" -ge 24 ] 2>/dev/null; then
    echo "  [ok] Docker version >= 24 (found $(docker version --format '{{.Server.Version}}' 2>/dev/null))"
else
    echo "  [!!] Docker version >= 24 required (found $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'unknown'))"
    echo "       BuildKit cache mounts in docker/dev/Dockerfile require Docker 24+."
    errors=$((errors + 1))
fi

echo ""

if [ "$errors" -gt 0 ]; then
    echo "$errors check(s) failed. Fix the above before continuing."
    echo ""
    echo "  Install Docker:          https://docs.docker.com/get-docker/"
    echo "  Upgrade Docker Desktop:  https://docs.docker.com/desktop/release-notes/"
    echo ""
    exit 1
fi

echo "All checks passed."
echo ""
