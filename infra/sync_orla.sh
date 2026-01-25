#!/bin/bash
# Sync orla binary to Lambda cluster
#
# Usage:
#   SSH_KEY=~/.ssh/id_rsa JUMPER_PASSWORD=... LAMBDA_PASSWORD=... ./infra/sync_orla.sh [lambda_host]
#
# Example:
#   ./infra/sync_orla.sh lambda1

set -e

# Source common setup code
SCRIPT_NAME="$(basename "$0")"
source "$(dirname "$0")/common.sh"

echo "Syncing orla binary to Lambda cluster: ${LAMBDA_HOST}"
echo "=================================================="

# Build orla for Linux
echo "Building orla for Linux..."
ORLA_BUILD_DIR=$(mktemp -d)
ORLA_BINARY="$ORLA_BUILD_DIR/orla"

# Check if ORLA_SOURCE_DIR is provided as environment variable
if [ -n "$ORLA_SOURCE_DIR" ] && [ -d "$ORLA_SOURCE_DIR" ] && [ -f "$ORLA_SOURCE_DIR/cmd/orla/main.go" ]; then
    # Use provided path
    ORLA_SOURCE_DIR_FOUND="$ORLA_SOURCE_DIR"
else
    # Try to find orla source directory in common locations
    ORLA_SOURCE_DIR_FOUND=""
    for possible_path in \
        "${SCRIPT_DIR}/../../orla" \
        "${SCRIPT_DIR}/../../../orla" \
        "$HOME/Projects/orla" \
        "$HOME/projects/orla" \
        "/Users/haydert/Projects/orla"; do
        if [ -d "$possible_path" ] && [ -f "$possible_path/cmd/orla/main.go" ]; then
            ORLA_SOURCE_DIR_FOUND="$possible_path"
            break
        fi
    done
fi

if [ -z "$ORLA_SOURCE_DIR_FOUND" ] || [ ! -d "$ORLA_SOURCE_DIR_FOUND" ] || [ ! -f "$ORLA_SOURCE_DIR_FOUND/cmd/orla/main.go" ]; then
    echo "Error: Cannot find orla source directory"
    echo "  Searched in: ${SCRIPT_DIR}/../../orla, ${SCRIPT_DIR}/../../../orla, $HOME/Projects/orla, etc."
    echo "  Set ORLA_SOURCE_DIR environment variable to specify the path"
    exit 1
fi

cd "$ORLA_SOURCE_DIR_FOUND"
echo "  Building orla from: $ORLA_SOURCE_DIR_FOUND"
echo "  This may take a minute on first build (downloading dependencies)..."

# Get version info
VERSION=$(git describe --tags --always --dirty 2>/dev/null || echo "dev")
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Build for Linux amd64
# Use timeout if available, otherwise just run the build
if command -v timeout >/dev/null 2>&1 || command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_CMD="timeout"
    [ -z "$(command -v timeout)" ] && TIMEOUT_CMD="gtimeout"
    echo "  Building with 5 minute timeout..."
    echo "  (You'll see Go module download progress if this is the first build)"
    if $TIMEOUT_CMD 5m bash -c "cd '$ORLA_SOURCE_DIR_FOUND' && GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -ldflags '-s -w -X main.version=$VERSION -X main.buildDate=$BUILD_DATE' -o '$ORLA_BINARY' ./cmd/orla" 2>&1 | tee /tmp/orla_build_$$.log; then
        if [ ! -f "$ORLA_BINARY" ]; then
            echo "  Error: Build command succeeded but binary not found"
            exit 1
        else
            ORLA_SIZE=$(du -h "$ORLA_BINARY" | cut -f1)
            echo "  Orla binary built successfully (size: $ORLA_SIZE, version: $VERSION)"
        fi
    else
        BUILD_EXIT=$?
        if [ $BUILD_EXIT -eq 124 ]; then
            echo "  Error: Build timed out after 5 minutes"
        else
            echo "  Error: Build failed with exit code $BUILD_EXIT"
        fi
        exit 1
    fi
else
    # No timeout command available, just run the build
    echo "  Building (no timeout available, this may take a while)..."
    echo "  (You'll see Go module download progress if this is the first build)"
    if GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build \
        -ldflags "-s -w -X main.version=$VERSION -X main.buildDate=$BUILD_DATE" \
        -o "$ORLA_BINARY" ./cmd/orla 2>&1 | tee /tmp/orla_build_$$.log; then
        if [ ! -f "$ORLA_BINARY" ]; then
            echo "  Error: Build command succeeded but binary not found"
            exit 1
        else
            ORLA_SIZE=$(du -h "$ORLA_BINARY" | cut -f1)
            echo "  Orla binary built successfully (size: $ORLA_SIZE, version: $VERSION)"
        fi
    else
        BUILD_EXIT=$?
        echo "  Error: Build failed with exit code $BUILD_EXIT"
        exit 1
    fi
fi
echo ""

# Use SSH port forwarding with local sshpass to create tunnels
ZU_TUNNEL_PORT=${ZU_TUNNEL_PORT:-$(python3 -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" 2>/dev/null || echo "10001")}
LAMBDA_TUNNEL_PORT=${LAMBDA_TUNNEL_PORT:-$(python3 -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()" 2>/dev/null || echo "10002")}

# Cleanup function - handles tunnels and orla build dir
cleanup() {
    lsof -ti:"${ZU_TUNNEL_PORT}" | xargs kill -9 2>/dev/null || true
    lsof -ti:"${LAMBDA_TUNNEL_PORT}" | xargs kill -9 2>/dev/null || true
    [ -n "$ORLA_BUILD_DIR" ] && [ -d "$ORLA_BUILD_DIR" ] && rm -rf "$ORLA_BUILD_DIR" 2>/dev/null || true
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

# Transfer and install the orla binary through the tunnel
echo "Transferring orla binary to Lambda cluster..."
cat "$ORLA_BINARY" | sshpass -p "$LAMBDA_PASSWORD" ssh -o StrictHostKeyChecking=no -p "${LAMBDA_TUNNEL_PORT}" $LAMBDA_USER@localhost \
    "mkdir -p ~/harvard-agentic-system/bin ~/.local/bin && \
     cat > ~/harvard-agentic-system/bin/orla && \
     chmod +x ~/harvard-agentic-system/bin/orla && \
     cp ~/harvard-agentic-system/bin/orla ~/.local/bin/orla && \
     chmod +x ~/.local/bin/orla && \
     PATH_ADD='export PATH=\"\$HOME/.local/bin:\$PATH\"' && \
     if ! grep -q '.local/bin' ~/.bashrc 2>/dev/null; then \
         echo \"\$PATH_ADD\" >> ~/.bashrc; \
     fi && \
     if [ -f ~/.profile ] && ! grep -q '.local/bin' ~/.profile 2>/dev/null; then \
         echo \"\$PATH_ADD\" >> ~/.profile; \
     fi"

echo ""
echo "Orla binary sync complete!"
echo ""
echo "Note: Orla binary has been installed to ~/.local/bin/orla"
echo "      and added to PATH in ~/.bashrc. You may need to run 'source ~/.bashrc'"
echo "      or start a new shell session for PATH changes to take effect."
