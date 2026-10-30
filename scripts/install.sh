#!/bin/sh
# Installs the `igforge` command and, optionally, the automatic weekly run.
#
#   ./scripts/install.sh              just the command
#   ./scripts/install.sh --weekly     plus an automatic Monday-morning run
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BIN="$HOME/bin"
PY=$(command -v python3)

mkdir -p "$BIN"

# No site-packages install: the wrapper points at the repo root.
cat > "$BIN/igforge" <<EOF
#!/bin/sh
export PYTHONPATH="$ROOT\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$PY" -m igforge "\$@"
EOF
chmod +x "$BIN/igforge"

echo "✓ $BIN/igforge"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "! $BIN is not on your PATH. Add to ~/.zshrc:  export PATH=\"\$HOME/bin:\$PATH\"" ;;
esac

"$BIN/igforge" init

if [ "${1:-}" = "--weekly" ]; then
  PLIST="$HOME/Library/LaunchAgents/com.igforge.weekly.plist"
  LOGS="$HOME/.igforge/logs"
  mkdir -p "$LOGS" "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.igforge.weekly</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string><string>-lc</string>
    <string>$BIN/igforge auto -n 3 &amp;&amp; osascript -e 'display notification "Posts ready in ~/.igforge/posts" with title "igforge"'</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$LOGS/weekly.log</string>
  <key>StandardErrorPath</key><string>$LOGS/weekly.err</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
EOF
  launchctl bootout "gui/$(id -u)/com.igforge.weekly" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "✓ weekly run: Mondays at 8:00 → $LOGS/weekly.log"
fi

echo
echo "Next step:  igforge brand --edit"
