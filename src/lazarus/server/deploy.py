"""Deployment scripts and templates for Hetzner server setup."""

from __future__ import annotations


def generate_setup_script(domain: str = "lazarus.dev") -> str:
    """Generate a bash script for initial Hetzner server setup."""
    return f"""\
#!/usr/bin/env bash
set -euo pipefail

echo "=== Lazarus Server Setup ==="

# Update system
apt-get update && apt-get upgrade -y

# Install dependencies
apt-get install -y docker.io docker-compose nginx certbot python3-certbot-nginx

# Enable docker
systemctl enable docker
systemctl start docker

# Get SSL certificate
certbot certonly --nginx -d {domain} --non-interactive --agree-tos -m admin@{domain}

# Create devpi data directory
mkdir -p /var/lib/devpi

echo "=== Setup complete. Deploy with docker-compose up -d ==="
"""


def generate_index_setup(
    server_url: str = "http://localhost:3141",
    user: str = "lazarus",
    password: str = "changeme",
) -> str:
    """Generate devpi index creation commands."""
    return f"""\
#!/usr/bin/env bash
set -euo pipefail

# Wait for devpi to be ready
echo "Waiting for devpi server..."
sleep 5

# Connect to devpi
devpi use {server_url}

# Create user
devpi user -c {user} password={password}

# Login
devpi login {user} --password={password}

# Create stable index (non-volatile, inherits from PyPI)
devpi index -c stable bases=root/pypi volatile=False mirror_whitelist='*'

# Create staging index (volatile, inherits from stable)
devpi index -c staging bases={user}/stable volatile=True

# Use stable as default
devpi use {user}/stable

echo "=== devpi indexes created ==="
echo "Stable: {server_url}/{user}/stable/+simple/"
echo "Staging: {server_url}/{user}/staging/+simple/"
echo ""
echo "To use with pip:"
echo "  pip install --index-url {server_url}/{user}/stable/+simple/ <package>"
"""
