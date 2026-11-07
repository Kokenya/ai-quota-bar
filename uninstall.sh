#!/usr/bin/env bash
set -e

echo "==> Uninstalling AI Quota Bar..."

systemctl --user stop ai-quota-bar.service 2>/dev/null || true
systemctl --user disable ai-quota-bar.service 2>/dev/null || true
systemctl --user stop ai-usage-indicator.service 2>/dev/null || true
systemctl --user disable ai-usage-indicator.service 2>/dev/null || true

rm -f "$HOME/.config/systemd/user/ai-quota-bar.service"
rm -f "$HOME/.config/systemd/user/ai-usage-indicator.service"
rm -f "$HOME/.config/autostart/ai-quota-bar.desktop"
rm -f "$HOME/.config/autostart/ai-usage-indicator.desktop"
rm -rf "$HOME/.local/share/gnome-shell/extensions/ai-quota-bar@kokenya"
rm -f "$HOME/.local/bin/ai-usage" "$HOME/.local/bin/ai-quota-bar"
rm -rf "$HOME/.cache/ai-quota-bar" "$HOME/.cache/ai-usage-monitor"
rm -rf "$HOME/.config/ai-usage-monitor"

systemctl --user daemon-reload

echo "==> AI Quota Bar successfully removed."
