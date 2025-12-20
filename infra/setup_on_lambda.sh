#!/bin/bash
# Setup script to run on the Lambda cluster
# This script is executed remotely via setup_lambda.sh

set -e

echo "Setting up Harvard Agentic System..."
echo ""

# Check Python version
echo "Python version:"
python3 --version
echo ""

# Check if uv is installed
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # uv installs to ~/.local/bin (not ~/.cargo/bin)
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    echo "uv installed successfully"
    echo ""
fi

# Ensure PATH includes uv's location (in case it was already installed)
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

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

# Sync dependencies
echo "Installing dependencies with uv..."
# Ensure PATH is set (uv might be in ~/.local/bin)
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
uv sync

echo ""
echo "=================================================="
echo "Setup complete!"
echo ""
echo "You can now run:"
echo "  cd ~/harvard-agentic-system"
echo "  uv run h-agent-sys run --model <model> --k <k> --c <c> --turns <turns>"
