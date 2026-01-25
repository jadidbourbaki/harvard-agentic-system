#!/bin/bash
# Setup script to run on the Lambda cluster
# This script is executed remotely via setup_lambda.sh

set -e

echo "Setting up Harvard Agentic System..."
echo ""

# Check if Go is installed
if ! command -v go &>/dev/null; then
    echo "Installing Go..."
    GO_VERSION="1.23.0"
    GO_ARCH="linux-amd64"
    GO_TAR="go${GO_VERSION}.${GO_ARCH}.tar.gz"
    GO_URL="https://go.dev/dl/${GO_TAR}"

    cd /tmp
    curl -LO "$GO_URL"
    sudo rm -rf /usr/local/go
    sudo tar -C /usr/local -xzf "$GO_TAR"
    rm "$GO_TAR"

    # Add Go to PATH
    export PATH="/usr/local/go/bin:$PATH"
    echo "export PATH=\"/usr/local/go/bin:\$PATH\"" >>~/.bashrc
    echo "export PATH=\"/usr/local/go/bin:\$PATH\"" >>~/.profile 2>/dev/null || true

    echo "Go ${GO_VERSION} installed successfully"
    echo ""
else
    echo "Go already installed:"
    go version
    echo ""
fi

# Ensure Go is in PATH
export PATH="/usr/local/go/bin:$PATH"

# Navigate to project directory
PROJECT_DIR="$HOME/harvard-agentic-system"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project directory not found at $PROJECT_DIR"
    echo "Please sync the repository first by running:"
    echo "  make sync-repo"
    exit 1
fi

cd "$PROJECT_DIR"
echo "Project directory: $PROJECT_DIR"
echo ""

# Install orla binary if it was synced
ORLA_SYNCED_PATH="$PROJECT_DIR/bin/orla"
ORLA_INSTALL_DIR="$HOME/.local/bin"

if [ -f "$ORLA_SYNCED_PATH" ]; then
    echo "Installing orla from synced binary..."
    mkdir -p "$ORLA_INSTALL_DIR"
    cp "$ORLA_SYNCED_PATH" "$ORLA_INSTALL_DIR/orla"
    chmod +x "$ORLA_INSTALL_DIR/orla"
    export PATH="$ORLA_INSTALL_DIR:$PATH"
    echo "  ✅ Orla installed to: $ORLA_INSTALL_DIR/orla"
    if command -v orla &>/dev/null; then
        orla --version 2>/dev/null || echo "  (Version check available)"
    fi
    echo ""
elif command -v orla &>/dev/null; then
    echo "Orla already installed in PATH:"
    orla --version
    echo ""
else
    echo "⚠️  Warning: Orla binary not found"
    echo "  Expected location: $ORLA_SYNCED_PATH"
    echo "  Make sure to run 'make sync-repo' first to sync the orla binary"
    echo ""
fi

# Check if Docker is installed (required for SGLang)
if ! command -v docker &>/dev/null; then
    echo "Installing Docker..."
    # Try to install Docker (may require sudo)
    if command -v apt-get &>/dev/null; then
        sudo apt-get update
        sudo apt-get install -y docker.io docker-compose
        sudo usermod -aG docker "$USER"
        echo "Docker installed. You may need to log out and back in for group changes to take effect."
    else
        echo "Warning: Docker not found and automatic installation not available for this system"
        echo "Please install Docker manually"
    fi
    echo ""
else
    echo "Docker already installed:"
    docker --version
    echo ""
fi

# No Python dependencies needed - SGLang runs in Docker

echo ""
echo "=================================================="
echo "Setup complete!"
echo ""
echo "Installed tools:"
if command -v orla &>/dev/null; then
    echo "  ✅ orla: $(orla --version 2>/dev/null || echo 'installed')"
else
    echo "  ⚠️  orla: not found in PATH (may need to add ~/.local/bin to PATH)"
fi
if command -v docker &>/dev/null; then
    echo "  ✅ docker: $(docker --version)"
else
    echo "  ⚠️  docker: not installed (required for SGLang)"
fi
echo ""
echo "Next steps:"
echo ""
echo "1. Start SGLang server using Docker (required before running experiments):"
echo "   tmux new -s sglang"
echo "   docker run --gpus all --shm-size 32g -p 30000:30000 \\"
echo "     -v ~/.cache/huggingface:/root/.cache/huggingface \\"
echo "     --ipc=host \\"
echo "     lmsysorg/sglang:latest python -m sglang.launch_server \\"
echo "     --model-path mistralai/Mistral-7B-Instruct-v0.3 --port 30000"
echo "   # Detach: Ctrl+B then D"
echo ""
echo "2. Run experiments:"
echo "   cd ~/harvard-agentic-system/experiments"
echo "   go run . --policy preserve --turns 100 --k 8"
echo ""
echo "Note: Orla does NOT start SGLang - you must start it manually first!"
echo "      The experiments expect SGLang running at http://localhost:30000"
