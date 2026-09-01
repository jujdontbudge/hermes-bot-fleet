#!/usr/bin/env bash
set -Eeuo pipefail
bot=${1:?usage: $0 chief|test-worker}
case "$bot" in chief) display='Chief'; username='johan_chief_bot';; test-worker) display='Test Worker'; username='johan_test_worker_bot';; *) exit 64;; esac
printf 'Open https://t.me/BotFather and send /newbot\nName: %s\nPreferred username: %s (use a clean no-digit variant if unavailable)\n' "$display" "$username"
printf 'Paste the BotFather token here (input is hidden): '
IFS= read -r -s token
printf '\n'
[[ $token =~ ^[0-9]{6,}:[A-Za-z0-9_-]{20,}$ ]] || { echo 'Token shape rejected; nothing written.' >&2; exit 78; }
dir="$HOME/.config/hermes-fleet"
install -d -m 0700 "$dir"
umask 077
printf '%s\n' "$token" >"$dir/$bot-telegram-token"
unset token
chmod 0600 "$dir/$bot-telegram-token"
printf 'Saved %s Telegram token securely at %s\n' "$display" "$dir/$bot-telegram-token"
