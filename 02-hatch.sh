#!/bin/bash
set -euxo pipefail
export PATH=/opt/flutter/bin:/usr/local/bin:$PATH
# hatch core (mirror repo; default hatch-dev/hatch is 404)
export HATCH_REPO=mario-chamuty/hatch
curl -fsSL https://raw.githubusercontent.com/mario-chamuty/hatch/main/install.sh | bash
# hatch-ios plugin binary
curl -fsSL -o /usr/local/bin/hatch-ios \
  https://github.com/mario-chamuty/hatch-ios-plugin/releases/download/v0.1.0/hatch-ios-x86_64-unknown-linux-gnu
chmod +x /usr/local/bin/hatch-ios
command -v hatch || ls -la /root/.hatch /root/.local/bin 2>/dev/null || true
hash -r
which hatch hatch-ios || true
hatch --version || true
hatch-ios --help || true
# el MinimumOSVersion viene fijo en 13.4 y Apple exigirá 15.0 desde 2027
python3 /out/02-minos.py "${MIN_OS:-15.0}"
echo "=== HATCH INSTALLED ==="
