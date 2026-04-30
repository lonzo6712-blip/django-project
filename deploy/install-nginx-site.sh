#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Usage: $0 <pre-tls|tls> <domain> [www-domain]" >&2
  exit 1
fi

MODE="$1"
DOMAIN="$2"
WWW_DOMAIN="${3:-www.$DOMAIN}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$MODE" in
  pre-tls)
    SOURCE_FILE="$SCRIPT_DIR/nginx-monettefarms.pre-tls.conf"
    ;;
  tls)
    SOURCE_FILE="$SCRIPT_DIR/nginx-monettefarms.conf"
    ;;
  *)
    echo "Invalid mode: $MODE" >&2
    exit 1
    ;;
esac

TARGET_FILE="/etc/nginx/sites-available/monettefarms"

sudo cp "$SOURCE_FILE" "$TARGET_FILE"
sudo sed -i "s/www\.your-domain\.example/$WWW_DOMAIN/g" "$TARGET_FILE"
sudo sed -i "s/your-domain\.example/$DOMAIN/g" "$TARGET_FILE"
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf "$TARGET_FILE" /etc/nginx/sites-enabled/monettefarms
sudo nginx -t
sudo systemctl reload nginx

echo "Installed $MODE Nginx config for $DOMAIN and $WWW_DOMAIN"
