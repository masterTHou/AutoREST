#!/usr/bin/env bash
# AutoREST DSH Skill — macOS / Linux Installer
# Usage: bash install.sh [target-project-dir]
#
# If target-project-dir is omitted, installs to current directory.
# Installs to: <target>/.dsh/skills/autorest/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$SCRIPT_DIR/.dsh/skills/autorest"
TARGET="${1:-$(pwd)}"
TARGET_DIR="$TARGET/.dsh/skills/autorest"

if [ ! -d "$SKILL_SRC" ]; then
  echo "ERROR: Skill source not found at $SKILL_SRC"
  echo "Make sure you run this script from the AutoREST project root."
  exit 1
fi

echo "==================================="
echo " AutoREST DSH Skill Installer"
echo "==================================="
echo ""
echo "Source: $SKILL_SRC"
echo "Target: $TARGET_DIR"
echo ""

mkdir -p "$TARGET_DIR"
cp -r "$SKILL_SRC"/* "$TARGET_DIR/"

echo "✅ AutoREST Skill installed to: $TARGET_DIR"
echo ""
echo "Next steps:"
echo "  1. Restart DSH (⌘Q and reopen)"
echo "  2. Say: '帮我算一个水分子的单点能'"
echo "  3. DSH will discover AutoREST and show selection panels"
echo ""