#!/usr/bin/env bash
# Keeps contact data private in a public repo.
#   vault.sh open  -> decrypts private.tar.enc into config.json, queue/, log/, pending/, EXCLUDE.txt
#   vault.sh seal  -> encrypts them back into private.tar.enc
# Key: env STATE_KEY (GitHub secret), else macOS Keychain item "outreach-state-key".
set -euo pipefail
cd "$(dirname "$0")/.."
KEY="${STATE_KEY:-$(security find-generic-password -s outreach-state-key -w 2>/dev/null || true)}"
[ -n "$KEY" ] || { echo "vault: no STATE_KEY"; exit 1; }
FILES="config.json queue/queue.csv log/sent.md pending EXCLUDE.txt"
case "${1:-}" in
  open) openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "pass:$KEY" -in private.tar.enc | tar -xzf - ;;
  seal) tar -czf - $FILES | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "pass:$KEY" -out private.tar.enc ;;
  *) echo "usage: vault.sh open|seal"; exit 2 ;;
esac
