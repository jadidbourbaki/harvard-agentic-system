#!/bin/bash
# Sync repository to Lambda cluster
#
# Usage:
#   SSH_KEY=~/.ssh/id_rsa JUMPER_PASSWORD=... LAMBDA_PASSWORD=... ./infra/sync_repo.sh [lambda_host]
#
# Example:
#   ./infra/sync_repo.sh lambda1

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
    echo "Usage: SSH_KEY=~/.ssh/id_rsa ./infra/sync_repo.sh"
    exit 1
fi

if [ ! -f "$SSH_KEY" ]; then
    echo "Error: SSH key file not found: $SSH_KEY"
    exit 1
fi

if [ -z "$JUMPER_PASSWORD" ]; then
    echo "Error: JUMPER_PASSWORD environment variable is not set"
    echo "Usage: export JUMPER_PASSWORD='your-password' && ./infra/sync_repo.sh"
    exit 1
fi

if [ -z "$LAMBDA_PASSWORD" ]; then
    echo "Error: LAMBDA_PASSWORD environment variable is not set"
    echo "Usage: export LAMBDA_PASSWORD='your-password' && ./infra/sync_repo.sh"
    exit 1
fi

# Check if sshpass is installed locally (needed for password authentication)
if ! command -v sshpass &>/dev/null; then
    echo "Error: sshpass is required locally but not installed."
    echo "Install with: brew install hudochenkov/sshpass/sshpass (macOS)"
    echo "              or: apt-get install sshpass (Linux)"
    exit 1
fi

echo "Syncing repository to Lambda cluster: ${LAMBDA_HOST}"
echo "=================================================="

# Create a temporary tar archive excluding unnecessary files
# Use process ID to ensure uniqueness
TEMP_TAR="/tmp/repo-sync-$$.tar.gz"
# Clean up any existing temp file for this process
rm -f "$TEMP_TAR" 2>/dev/null || true

# Use SSH port forwarding with local sshpass to create tunnels
ZU_TUNNEL_PORT=${ZU_TUNNEL_PORT:-$(python3 -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" 2>/dev/null || echo "10001")}
LAMBDA_TUNNEL_PORT=${LAMBDA_TUNNEL_PORT:-$(python3 -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" 2>/dev/null || echo "10002")}

# Cleanup function - handles both temp file and tunnels
cleanup() {
    rm -f "$TEMP_TAR" 2>/dev/null || true
    lsof -ti:"${ZU_TUNNEL_PORT}" | xargs kill -9 2>/dev/null || true
    lsof -ti:"${LAMBDA_TUNNEL_PORT}" | xargs kill -9 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Creating archive..."
cd "$PROJECT_ROOT"
# Use --no-xattrs to exclude macOS extended attributes (avoids warnings on Linux)
tar -czf "$TEMP_TAR" \
    --no-xattrs \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.pytest_cache' \
    --exclude='.mypy_cache' \
    --exclude='.git' \
    --exclude='results.json' \
    --exclude='*.log' \
    --exclude='models' \
    --exclude='.cache' \
    --exclude='.agent-context' \
    --exclude='*.tar.gz' \
    .

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

# Transfer and extract the archive through the tunnel
# Pipe the tar directly through stdin instead of base64 encoding (avoids argument length limits)
echo "Transferring and extracting on Lambda cluster..."
cat "$TEMP_TAR" | sshpass -p "$LAMBDA_PASSWORD" ssh -o StrictHostKeyChecking=no -p "${LAMBDA_TUNNEL_PORT}" $LAMBDA_USER@localhost \
    "mkdir -p ~/harvard-agentic-system && cd ~/harvard-agentic-system && tar -xzf -"

echo ""
echo "Repository sync complete!"
