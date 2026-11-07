#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
AUTOSTART_DIR="$HOME/.config/autostart"
GNOME_EXT_DIR="$HOME/.local/share/gnome-shell/extensions/ai-quota-bar@kokenya"

echo "==> Installing AI Quota Bar..."

# 1. Ensure directories exist
mkdir -p "$BIN_DIR" "$SYSTEMD_USER_DIR" "$AUTOSTART_DIR" "$GNOME_EXT_DIR"

# 2. Stop and remove old legacy indicator service if present
systemctl --user stop ai-usage-indicator.service 2>/dev/null || true
systemctl --user disable ai-usage-indicator.service 2>/dev/null || true
rm -f "$SYSTEMD_USER_DIR/ai-usage-indicator.service"
rm -f "$AUTOSTART_DIR/ai-usage-indicator.desktop"
rm -rf "$HOME/.config/ai-usage-monitor" "$HOME/.cache/ai-usage-monitor"

# 3. Create entrypoint scripts in ~/.local/bin
cat << 'EOF' > "$BIN_DIR/ai-usage"
#!/usr/bin/python3
import sys, os
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
# Check if running from repo or installed location
REPO_DIR = os.path.expanduser("~/gh/ai-quota-bar/src")
if os.path.exists(REPO_DIR):
    sys.path.insert(0, REPO_DIR)
from ai_quota_bar.cli import main
if __name__ == "__main__":
    main()
EOF
chmod +x "$BIN_DIR/ai-usage"

cat << 'EOF' > "$BIN_DIR/ai-quota-bar"
#!/usr/bin/python3
import sys, os
REPO_DIR = os.path.expanduser("~/gh/ai-quota-bar/src")
if os.path.exists(REPO_DIR):
    sys.path.insert(0, REPO_DIR)
from ai_quota_bar.indicator import main
if __name__ == "__main__":
    main()
EOF
chmod +x "$BIN_DIR/ai-quota-bar"

# 4. Install systemd service
cp "$SCRIPT_DIR/systemd/ai-quota-bar.service" "$SYSTEMD_USER_DIR/ai-quota-bar.service"
systemctl --user daemon-reload
systemctl --user enable ai-quota-bar.service
systemctl --user restart ai-quota-bar.service

# 5. Install autostart entry
cp "$SCRIPT_DIR/autostart/ai-quota-bar.desktop" "$AUTOSTART_DIR/ai-quota-bar.desktop"

# 6. Remove any conflicting legacy GNOME shell extensions
gnome-extensions uninstall ai-quota-bar@kokenya 2>/dev/null || true
gnome-extensions uninstall ai-usage-monitor@relkokeny 2>/dev/null || true
rm -rf "$HOME/.local/share/gnome-shell/extensions/ai-quota-bar@kokenya"
rm -rf "$HOME/.local/share/gnome-shell/extensions/ai-usage-monitor@relkokeny"

echo "==> Installation complete!"
echo "   - CLI command: ai-usage"
echo "   - Top bar indicator: Running via systemd (ai-quota-bar.service)"
echo "   - Status check: systemctl --user status ai-quota-bar.service"
