#!/bin/bash
# Connect script for Harvard Agentic System Lambda cluster
#
# Usage:
#   SSH_KEY=~/.ssh/id_rsa JUMPER_PASSWORD=... LAMBDA_PASSWORD=... ./infra/connect_lambda.sh [lambda_host]
#
# Example:
#   ./infra/connect_lambda.sh lambda1

set -e

# Source common setup code
SCRIPT_NAME="$(basename "$0")"
source "$(dirname "$0")/common.sh"

echo "Connecting to Lambda cluster: ${LAMBDA_HOST}"
echo "=========================================="

# Use SSH port forwarding with local sshpass to create tunnels
# This allows us to connect through the chain using only local sshpass

# Find available local ports (fallback if python not available)
ZU_TUNNEL_PORT=${ZU_TUNNEL_PORT:-$(python3 -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" 2>/dev/null || echo "10001")}
LAMBDA_TUNNEL_PORT=${LAMBDA_TUNNEL_PORT:-$(python3 -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" 2>/dev/null || echo "10002")}

# Cleanup function - find and kill SSH processes using these ports
cleanup() {
    lsof -ti:"${ZU_TUNNEL_PORT}" | xargs kill -9 2>/dev/null || true
    lsof -ti:"${LAMBDA_TUNNEL_PORT}" | xargs kill -9 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Create tunnel from local to zu through jumper (using local sshpass)
echo "Setting up tunnel to zu..."
sshpass -p "$JUMPER_PASSWORD" ssh -i "$SSH_KEY" \
    -o StrictHostKeyChecking=no \
    -f -N -L "${ZU_TUNNEL_PORT}":localhost:${ZU_PORT} \
    -p $JUMPER_PORT $JUMPER_HOST
sleep 2

# Create tunnel from local to lambda through zu (using JUMPER_PASSWORD to connect to zu)
echo "Setting up tunnel to lambda..."
sshpass -p "$JUMPER_PASSWORD" ssh \
    -o StrictHostKeyChecking=no \
    -f -N -L "${LAMBDA_TUNNEL_PORT}":"${LAMBDA_HOST}".int.seas.harvard.edu:22 \
    -p "${ZU_TUNNEL_PORT}" guest@localhost
sleep 2

# Connect to lambda through the tunnel (lambda still requires password)
echo "Connecting to lambda..."
sshpass -p "$LAMBDA_PASSWORD" ssh -o StrictHostKeyChecking=no -p "${LAMBDA_TUNNEL_PORT}" $LAMBDA_USER@localhost
