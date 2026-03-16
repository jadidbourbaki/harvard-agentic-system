#!/bin/bash
# Sync Orla demo MP4s from Lambda cluster to local machine
#
# Usage:
#   SSH_KEY=~/.ssh/id_rsa JUMPER_PASSWORD=... LAMBDA_PASSWORD=... ./infra/sync_demo.sh [lambda_host]
#
# Example:
#   ./infra/sync_demo.sh lambda1

set -e

# Source common setup code
SCRIPT_NAME="$(basename "$0")"
source "$(dirname "$0")/common.sh"

echo "Syncing demo MP4s from Lambda cluster: ${LAMBDA_HOST}"
echo "=================================================="

# Use SSH port forwarding with local sshpass to create tunnels
ZU_TUNNEL_PORT=${ZU_TUNNEL_PORT:-$(python3 -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" 2>/dev/null || echo "10001")}
LAMBDA_TUNNEL_PORT=${LAMBDA_TUNNEL_PORT:-$(python3 -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" 2>/dev/null || echo "10002")}

# Cleanup function - handles tunnels
cleanup() {
    lsof -ti:"${ZU_TUNNEL_PORT}" | xargs kill -9 2>/dev/null || true
    lsof -ti:"${LAMBDA_TUNNEL_PORT}" | xargs kill -9 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Create tunnel from local to zu through jumper
echo "Setting up tunnel to zu..."
sshpass -p "$JUMPER_PASSWORD" ssh -i "$SSH_KEY" \
    -o StrictHostKeyChecking=no \
    -f -N -L "${ZU_TUNNEL_PORT}":localhost:${ZU_PORT} \
    -p $JUMPER_PORT $JUMPER_HOST
sleep 2

# Create tunnel from local to lambda through zu
echo "Setting up tunnel to lambda..."
sshpass -p "$JUMPER_PASSWORD" ssh \
    -o StrictHostKeyChecking=no \
    -f -N -L "${LAMBDA_TUNNEL_PORT}":"${LAMBDA_HOST}".int.seas.harvard.edu:22 \
    -p "${ZU_TUNNEL_PORT}" guest@localhost
sleep 2

# Create local output directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/output"

# Copy all MP4s from Lambda (orla share/) to local output/
echo "Syncing *.mp4 from ~/orla/share/..."
sshpass -p "$LAMBDA_PASSWORD" scp -o StrictHostKeyChecking=no -P "${LAMBDA_TUNNEL_PORT}" \
    "${LAMBDA_USER}@localhost:~/orla/share/*.mp4" \
    "$PROJECT_ROOT/output/"

echo ""
echo "Demo sync complete! Videos are in output/"
