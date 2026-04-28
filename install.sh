#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing PrintFlow..."

mkdir -p ~/.local/bin
mkdir -p ~/.local/share/icons
mkdir -p ~/.local/share/applications

cp "$SCRIPT_DIR/printflow.py" ~/.local/bin/printflow.py
chmod +x ~/.local/bin/printflow.py

cp "$SCRIPT_DIR/printflow.svg" ~/.local/share/icons/printflow.svg

EXEC_PATH="$HOME/.local/bin/printflow.py"

cat > ~/.local/share/applications/printflow.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=PrintFlow
Comment=Photo print manager for Linux
Exec=python3 ${EXEC_PATH}
Icon=printflow
Terminal=false
Categories=Graphics;Photography;
Keywords=print;photo;printer;turboprint;
EOF

update-desktop-database ~/.local/share/applications 2>/dev/null || true

echo ""
echo "PrintFlow installed successfully!"
echo ""
echo "You can now:"
echo "  - Find PrintFlow in your applications menu"
echo "  - Run it directly: python3 ~/.local/bin/printflow.py"
echo ""
echo "Requirements:"
echo "  - TurboPrint must be installed (see https://www.turboprint.info/)"
echo "  - sudo apt install python3-gi python3-gi-cairo imagemagick"
