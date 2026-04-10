#!/bin/bash
# OMEGA PROTOCOL — Developer Setup Script
# Stabilizes the environment for Python 3.14 + VS Code

set -e

echo "=== OMEGA4 ENVIRONMENTAL STABILIZATION ==="

# 1. Verify Virtual Environment
if [ ! -d ".venv" ]; then
    echo "Creating .venv (Python 3.14)..."
    python3.14 -m venv .venv
fi

# 2. Setup VS Code Settings (Absolute Resolution)
echo "Configuring .vscode/settings.json..."
mkdir -p .vscode
cat <<EOF > .vscode/settings.json
{
    "python.defaultInterpreterPath": "$(pwd)/.venv/bin/python",
    "python.analysis.extraPaths": [
        "$(pwd)/backend",
        "$(pwd)/scripts"
    ],
    "python.terminal.activateEnvInCurrentTerminal": true
}
EOF

# 3. Install Dependencies
echo "Installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# 4. Verify Pydantic V2
echo "Verifying environment sanity..."
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
python3 -c "import pydantic; print(f'Pydantic version: {pydantic.VERSION}')"

echo "=== STABILIZATION COMPLETE ==="
echo "Please reload your IDE to apply new interpreter settings."
