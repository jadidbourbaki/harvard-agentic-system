#!/bin/bash
# Connect script for Harvard Agentic System Lambda cluster
#
# Usage:
#   SSH_KEY=~/.ssh/id_rsa JUMPER_PASSWORD=... LAMBDA_PASSWORD=... ./infra/connect_lambda.sh [lambda_host]
#
# Example:
#   ./infra/connect_lambda.sh lambda1

set -e

# Configuration
JUMPER_HOST="guest@ec2-3-84-159-179.compute-1.amazonaws.com"
JUMPER_PORT=23219
ZU_PORT=23218
LAMBDA_HOST="${1:-lambda1}"
LAMBDA_USER="hayder"

# Check for required environment variables
if [ -z "$SSH_KEY" ]; then
    echo "Error: SSH_KEY environment variable is not set"
    echo "Usage: SSH_KEY=~/.ssh/id_rsa ./infra/connect_lambda.sh"
    exit 1
fi

if [ ! -f "$SSH_KEY" ]; then
    echo "Error: SSH key file not found: $SSH_KEY"
    exit 1
fi

if [ -z "$JUMPER_PASSWORD" ]; then
    echo "Error: JUMPER_PASSWORD environment variable is not set"
    echo "Usage: export JUMPER_PASSWORD='your-password' && ./infra/connect_lambda.sh"
    exit 1
fi

if [ -z "$LAMBDA_PASSWORD" ]; then
    echo "Error: LAMBDA_PASSWORD environment variable is not set"
    echo "Usage: export LAMBDA_PASSWORD='your-password' && ./infra/connect_lambda.sh"
    exit 1
fi

# Check if sshpass is installed locally (needed for password authentication)
if ! command -v sshpass &>/dev/null; then
    echo "Error: sshpass is required locally but not installed."
    echo "Install with: brew install hudochenkov/sshpass/sshpass (macOS)"
    echo "              or: apt-get install sshpass (Linux)"
    exit 1
fi

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
