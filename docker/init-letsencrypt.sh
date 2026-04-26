#!/usr/bin/env bash
# Obtain the initial Let's Encrypt certificate.
#
# Run ONCE on the EC2 instance after docker compose is set up:
#   DOMAIN=yourdomain.com EMAIL=you@example.com bash docker/init-letsencrypt.sh
#
# After this, certbot auto-renews via the certbot container.
set -euo pipefail

DOMAIN="${DOMAIN:?Set DOMAIN (e.g. DOMAIN=quant.example.com)}"
EMAIL="${EMAIL:?Set EMAIL for Let's Encrypt notifications}"
STAGING="${STAGING:-0}"

COMPOSE="docker compose"
DATA_PATH="certbot-conf"

staging_arg=""
if [[ "$STAGING" == "1" ]]; then
  staging_arg="--staging"
  echo "*** Using Let's Encrypt STAGING (test certs, not browser-trusted) ***"
fi

echo "=== Requesting certificate for ${DOMAIN} ==="

# 1. Create a temporary self-signed cert so nginx can start on 443
echo "  Creating temporary self-signed certificate..."
$COMPOSE run --rm --entrypoint "" certbot sh -c "
  mkdir -p /etc/letsencrypt/live/${DOMAIN}
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout /etc/letsencrypt/live/${DOMAIN}/privkey.pem \
    -out    /etc/letsencrypt/live/${DOMAIN}/fullchain.pem \
    -subj   '/CN=localhost'
"

# 2. Start nginx (needs a cert to boot the 443 block)
echo "  Starting nginx..."
$COMPOSE up -d nginx
sleep 5

# 3. Delete the temporary cert and request a real one
echo "  Requesting real certificate from Let's Encrypt..."
$COMPOSE run --rm --entrypoint "" certbot sh -c "
  rm -rf /etc/letsencrypt/live/${DOMAIN}
  rm -rf /etc/letsencrypt/archive/${DOMAIN}
  rm -rf /etc/letsencrypt/renewal/${DOMAIN}.conf
"

$COMPOSE run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  --email "$EMAIL" \
  --agree-tos --no-eff-email \
  -d "$DOMAIN" \
  $staging_arg

# 4. Reload nginx to pick up the real cert
echo "  Reloading nginx..."
$COMPOSE exec nginx nginx -s reload

echo ""
echo "=== Done. Certificate for ${DOMAIN} is live. ==="
echo "    Auto-renewal runs in the certbot container every 12h."
