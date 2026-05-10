#!/bin/bash
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/ollama-session"
BIN_DIR="$HOME/.local/bin"
BIN_PATH="$BIN_DIR/ollama-session"
VENV_DIR="$INSTALL_DIR/venv"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing ollama-session to $INSTALL_DIR"

mkdir -p "$INSTALL_DIR" "$BIN_DIR"

cp "$SCRIPT_DIR/ollama-session.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/widgets" "$INSTALL_DIR/"

echo "Creating virtual environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

cat > "$BIN_PATH" <<EOF
#!/bin/bash
exec "$VENV_DIR/bin/python" "$INSTALL_DIR/ollama-session.py" "\$@"
EOF
chmod +x "$BIN_PATH"

echo "Installed: $BIN_PATH"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "  $BIN_DIR is not in your PATH."
    echo "  Add this line to your ~/.zshrc or ~/.bashrc:"
    echo ""
    echo '    export PATH="$HOME/.local/bin:$PATH"'
fi
