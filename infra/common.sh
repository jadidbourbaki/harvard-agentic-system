#!/bin/bash
# Common setup code for Lambda cluster scripts
# This file should be sourced by other scripts, not executed directly
#
# Usage in calling script:
#   SCRIPT_NAME="$(basename "$0")"
#   source "$(dirname "$0")/common.sh"

# Configuration
JUMPER_HOST="guest@ec2-3-84-159-179.compute-1.amazonaws.com"
JUMPER_PORT=23219
ZU_PORT=23218
LAMBDA_HOST="${1:-lambda1}"
LAMBDA_USER="hayder"

# Get the directory where the calling script is located
# When sourced, ${BASH_SOURCE[0]} is this file, ${BASH_SOURCE[1]} is the caller
if [ -n "${BASH_SOURCE[1]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
else
    # Fallback if called directly (shouldn't happen)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Get script name for error messages
if [ -n "${SCRIPT_NAME:-}" ]; then
    SCRIPT_BASENAME="$SCRIPT_NAME"
elif [ -n "${BASH_SOURCE[1]}" ]; then
    SCRIPT_BASENAME="$(basename "${BASH_SOURCE[1]}")"
else
    SCRIPT_BASENAME="script"
fi

# Check for required environment variables
if [ -z "$SSH_KEY" ]; then
    echo "Error: SSH_KEY environment variable is not set"
    echo "Usage: SSH_KEY=~/.ssh/id_rsa ./infra/$SCRIPT_BASENAME"
    exit 1
fi

if [ ! -f "$SSH_KEY" ]; then
    echo "Error: SSH key file not found: $SSH_KEY"
    exit 1
fi

if [ -z "$JUMPER_PASSWORD" ]; then
    echo "Error: JUMPER_PASSWORD environment variable is not set"
    echo "Usage: export JUMPER_PASSWORD='your-password' && ./infra/$SCRIPT_BASENAME"
    exit 1
fi

if [ -z "$LAMBDA_PASSWORD" ]; then
    echo "Error: LAMBDA_PASSWORD environment variable is not set"
    echo "Usage: export LAMBDA_PASSWORD='your-password' && ./infra/$SCRIPT_BASENAME"
    exit 1
fi

# Check if sshpass is installed locally (needed for password authentication)
if ! command -v sshpass &>/dev/null; then
    echo "Error: sshpass is required locally but not installed."
    echo "Install with: brew install hudochenkov/sshpass/sshpass (macOS)"
    echo "              or: apt-get install sshpass (Linux)"
    exit 1
fi
