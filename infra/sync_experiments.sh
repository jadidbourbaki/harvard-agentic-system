#!/bin/bash
# Sync experiments/output/ directory from Lambda cluster to local machine
#
# Usage:
#   SSH_KEY=~/.ssh/id_rsa JUMPER_PASSWORD=... LAMBDA_PASSWORD=... ./infra/sync_experiments.sh [lambda_host]
#
# Example:
#   ./infra/sync_experiments.sh lambda1

set -e

# Configuration
JUMPER_HOST="guest@ec2-3-84-159-179.compute-1.amazonaws.com"
JUMPER_PORT=23219
ZU_PORT=23218
LAMBDA_HOST="${1:-lambda1}"
LAMBDA_USER="hayder"

# Get the project root directory (parent of infra/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check for required environment variables
if [ -z "$SSH_KEY" ]; then
    echo "Error: SSH_KEY environment variable is not set"
    echo "Usage: SSH_KEY=~/.ssh/id_rsa ./infra/sync_experiments.sh"
    exit 1
fi

if [ ! -f "$SSH_KEY" ]; then
    echo "Error: SSH key file not found: $SSH_KEY"
    exit 1
fi

if [ -z "$JUMPER_PASSWORD" ]; then
    echo "Error: JUMPER_PASSWORD environment variable is not set"
    echo "Usage: export JUMPER_PASSWORD='your-password' && ./infra/sync_experiments.sh"
    exit 1
fi

if [ -z "$LAMBDA_PASSWORD" ]; then
    echo "Error: LAMBDA_PASSWORD environment variable is not set"
    echo "Usage: export LAMBDA_PASSWORD='your-password' && ./infra/sync_experiments.sh"
    exit 1
fi

# Check if sshpass is installed locally (needed for password authentication)
if ! command -v sshpass &>/dev/null; then
    echo "Error: sshpass is required locally but not installed."
    echo "Install with: brew install hudochenkov/sshpass/sshpass (macOS)"
    echo "              or: apt-get install sshpass (Linux)"
    exit 1
fi

# Check if rsync is installed
if ! command -v rsync &>/dev/null; then
    echo "Error: rsync is required but not installed."
    echo "Install with: brew install rsync (macOS)"
    echo "              or: apt-get install rsync (Linux)"
    exit 1
fi

echo "Syncing experiments/output/ from Lambda cluster: ${LAMBDA_HOST}"
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

# Create local experiments/output directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/experiments/output"

# Sync experiments/output/ from Lambda to local using rsync
echo "Syncing experiments/output/..."
sshpass -p "$LAMBDA_PASSWORD" rsync -avz --progress \
    -e "ssh -o StrictHostKeyChecking=no -p ${LAMBDA_TUNNEL_PORT}" \
    "${LAMBDA_USER}@localhost:~/harvard-agentic-system/experiments/output/" \
    "$PROJECT_ROOT/experiments/output/"

echo ""
echo "Experiments sync complete! Results are in experiments/output/"
