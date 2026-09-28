#!/usr/bin/env bash
# Links this checkout's panel into the Omarchy plugin folder and puts it on
# the bar - where the old command widget ("assignmentvibe", which ran
# `assignmentvibe pick`) was, if it is still there; that one is removed.
# Safe to run again.
set -euo pipefail

plugin="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
id="felix.assignmentvibe"
target="$HOME/.config/omarchy/plugins/$id"
shell_json="$HOME/.config/omarchy/shell.json"

if [[ -e $target && ! -L $target ]]; then
  echo "$target exists and is not a link; move it away first." >&2
  exit 1
fi

mkdir -p "$(dirname "$target")"
ln -sfn "$plugin" "$target"
echo "linked $target -> $plugin"

omarchy-shell shell rescanPlugins >/dev/null
sleep 1

old_widget=false
if [[ -f $shell_json ]] && jq -e '[.bar.layout[]?[]? | select(.id == "assignmentvibe")] | length > 0' \
    "$shell_json" >/dev/null 2>&1; then
  old_widget=true
fi

if $old_widget; then
  omarchy plugin enable "$id" --before assignmentvibe
  cp "$shell_json" "$shell_json.before-assignmentvibe-panel"
  tmp="$(mktemp)"
  jq '.bar.layout |= map_values(map(select(.id != "assignmentvibe")))' "$shell_json" >"$tmp"
  mv "$tmp" "$shell_json"
  echo "replaced the old command widget (backup: $shell_json.before-assignmentvibe-panel)"
  rm -f "$HOME/.config/omarchy/bar/scripts/assignmentvibe"
else
  omarchy plugin enable "$id" "$@"
fi
