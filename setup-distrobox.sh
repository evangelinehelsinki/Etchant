#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="etchant-dev"
IMAGE="docker.io/library/ubuntu:24.04"

echo "=== Etchant Development Environment Setup ==="
echo "Container: $CONTAINER_NAME"
echo "Base image: $IMAGE"
echo ""

# Create the distrobox container
if distrobox list 2>/dev/null | grep -q "$CONTAINER_NAME"; then
    echo "Container '$CONTAINER_NAME' already exists. Entering to update..."
else
    echo "Creating container '$CONTAINER_NAME'..."
    distrobox create \
        --name "$CONTAINER_NAME" \
        --image "$IMAGE" \
        --additional-packages "software-properties-common curl git"
fi

# Install all dependencies inside the container
distrobox enter "$CONTAINER_NAME" -- bash -c '
    set -euo pipefail

    echo "--- Installing system packages ---"

    # Add KiCad PPA for KiCad 9
    if ! grep -q "kicad" /etc/apt/sources.list.d/*.list 2>/dev/null; then
        sudo add-apt-repository -y ppa:kicad/kicad-9.0-releases
    fi
    sudo apt-get update

    sudo apt-get install -y \
        kicad \
        kicad-libraries \
        python3-pip \
        python3-venv \
        python3-dev \
        python3-pcbnew \
        ngspice \
        libngspice0-dev \
        build-essential

    echo "--- Installing uv ---"
    if ! command -v uv &>/dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi

    echo "--- Setting up KiCad environment variables ---"
    KICAD_SYMBOL_DIR="/usr/share/kicad/symbols"
    KICAD_FOOTPRINT_DIR="/usr/share/kicad/footprints"

    # Add to bashrc if not already present
    if ! grep -q "KICAD_SYMBOL_DIR" ~/.bashrc 2>/dev/null; then
        cat >> ~/.bashrc << ENVEOF

# KiCad environment for Etchant / SKiDL
export KICAD_SYMBOL_DIR="$KICAD_SYMBOL_DIR"
export KICAD8_FOOTPRINT_DIR="$KICAD_FOOTPRINT_DIR"
export KICAD_FOOTPRINT_DIR="$KICAD_FOOTPRINT_DIR"
ENVEOF
    fi

    export KICAD_SYMBOL_DIR
    export KICAD8_FOOTPRINT_DIR="$KICAD_FOOTPRINT_DIR"
    export KICAD_FOOTPRINT_DIR="$KICAD_FOOTPRINT_DIR"

    echo "--- Installing project dependencies ---"
    cd /home/evangeline/Projects/etchant
    uv sync --all-extras

    echo ""
    echo "=== Setup complete ==="
    echo "KiCad symbols: $KICAD_SYMBOL_DIR"
    echo "KiCad footprints: $KICAD_FOOTPRINT_DIR"
    echo ""
    echo "Verify with:"
    echo "  uv run pytest tests/ -v"
    echo "  uv run etchant --help"
'

echo ""
echo "Container '$CONTAINER_NAME' is ready."
echo "Enter with: distrobox enter $CONTAINER_NAME"
echo "Then: cd /home/evangeline/Projects/etchant && uv run pytest"
