#!/bin/bash
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/bal"
BIN_DIR="$HOME/.local/bin"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing bal to $INSTALL_DIR"

cp -r "$SCRIPT_DIR/bal" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/pyproject.toml" "$INSTALL_DIR/"

echo "Creating virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
"$INSTALL_DIR/venv/bin/pip" install -q "$INSTALL_DIR"

cat > "$BIN_DIR/bal" <<EOF
#!/bin/bash
exec "$INSTALL_DIR/venv/bin/bal" "\$@"
EOF
chmod +x "$BIN_DIR/bal"

echo "Installed: $BIN_DIR/bal"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "  $BIN_DIR is not in your PATH."
    echo "  Add this line to your ~/.zshrc or ~/.bashrc:"
    echo ""
    echo '    export PATH="$HOME/.local/bin:$PATH"'
fi
