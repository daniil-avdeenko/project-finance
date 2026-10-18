#!/usr/bin/env bash
#
# Устанавливает локальные git-хуки из scripts/hooks/ в .git/hooks/.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

cp scripts/hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push

echo "Pre-push hook installed at .git/hooks/pre-push"
