"""Generate devpi and nginx configuration files."""

from __future__ import annotations


def generate_devpi_config(
    data_dir: str = "/var/lib/devpi",
    port: int = 3141,
    host: str = "0.0.0.0",
) -> str:
    """Generate devpi-server configuration."""
    return f"""\
[devpi-server]
serverdir = {data_dir}
port = {port}
host = {host}
restrict-modify = root
"""


def generate_nginx_config(
    server_name: str = "lazarus.dev",
    devpi_port: int = 3141,
    ssl: bool = True,
) -> str:
    """Generate nginx reverse proxy configuration for devpi."""
    ssl_block = ""
    if ssl:
        ssl_block = f"""\
    listen 443 ssl http2;
    ssl_certificate /etc/letsencrypt/live/{server_name}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{server_name}/privkey.pem;

"""

    return f"""\
server {{
    server_name {server_name};
    {ssl_block}\
    client_max_body_size 100M;

    location / {{
        proxy_pass http://127.0.0.1:{devpi_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-outside-url $scheme://$host;
    }}
}}
"""


def generate_docker_compose(devpi_version: str = "6.12") -> str:
    """Generate docker-compose.yml for devpi server."""
    return f"""\
version: "3.8"

services:
  devpi:
    image: devpi/devpi-server:{devpi_version}
    ports:
      - "3141:3141"
    volumes:
      - devpi-data:/var/lib/devpi
    restart: unless-stopped
    environment:
      - DEVPI_SERVERDIR=/var/lib/devpi

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - devpi
    restart: unless-stopped

volumes:
  devpi-data:
"""
