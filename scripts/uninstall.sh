#!/bin/sh
# Removes the command and the automation. Your data in ~/.igforge stays.
set -eu
launchctl bootout "gui/$(id -u)/com.igforge.weekly" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.igforge.weekly.plist"
rm -f "$HOME/bin/igforge"
echo "✓ removed. Your posts are still in ~/.igforge (delete them by hand if you want)."
