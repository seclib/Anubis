#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

app_name="${ANUBIS_DESKTOP_NAME:-Anubis Desktop OS}"
desktop_id="${ANUBIS_DESKTOP_ID:-Anubis.desktop}"
install_dir="${ANUBIS_INSTALL_DIR:-$repo_root}"
launcher_script="${ANUBIS_LAUNCHER_SCRIPT:-$install_dir/scripts/launch_anubis_desktop.sh}"
icon_source="${ANUBIS_ICON_SOURCE:-$repo_root/assets/icons/anubis.svg}"
icon_name="${ANUBIS_ICON_NAME:-anubis}"
applications_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons_dir="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
desktop_target="$applications_dir/$desktop_id"
icon_target="$icons_dir/$icon_name.svg"

if [[ ! -f "$repo_root/Anubis.desktop" ]]; then
  printf 'Missing desktop template: %s\n' "$repo_root/Anubis.desktop" >&2
  exit 1
fi

if [[ ! -f "$icon_source" ]]; then
  printf 'Missing icon source: %s\n' "$icon_source" >&2
  exit 1
fi

mkdir -p "$applications_dir" "$icons_dir"
mkdir -p "$(dirname -- "$launcher_script")"
if [[ "$(realpath -m "$repo_root/scripts/launch_anubis_desktop.sh")" != "$(realpath -m "$launcher_script")" ]]; then
  install -m 0755 "$repo_root/scripts/launch_anubis_desktop.sh" "$launcher_script"
else
  chmod 0755 "$launcher_script"
fi
install -m 0644 "$icon_source" "$icon_target"

escaped_exec="${launcher_script//\\/\\\\}"
escaped_exec="${escaped_exec//\"/\\\"}"
escaped_name="${app_name//\\/\\\\}"
escaped_name="${escaped_name//\"/\\\"}"

sed \
  -e "s|^Name=.*|Name=$escaped_name|" \
  -e "s|^Exec=.*|Exec=env ANUBIS_INSTALL_DIR=\"$install_dir\" \"$escaped_exec\"|" \
  -e "s|^Icon=.*|Icon=$icon_name|" \
  "$repo_root/Anubis.desktop" > "$desktop_target"

chmod 0644 "$desktop_target"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$applications_dir" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" >/dev/null 2>&1 || true
fi

if command -v xdg-desktop-menu >/dev/null 2>&1; then
  xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi

printf 'Installed %s\n' "$desktop_target"
printf 'Installed %s\n' "$icon_target"
printf 'Launcher command: %s\n' "$launcher_script"
