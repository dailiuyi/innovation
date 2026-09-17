"""Generate private Compose configuration without printing secrets or replacing files."""
import argparse
import ipaddress
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-bytes', type=int, required=True,
                        help='Explicit storage test limit; not a frozen artifact upload contract')
    parser.add_argument('--test', action='store_true', help='Use isolated test config and port 18082')
    parser.add_argument('--bind-address', default='127.0.0.1',
                        help='IPv4/IPv6 host address for the gateway; ignored with --test')
    parser.add_argument('--http-port', type=int, default=18081,
                        help='Host port for the gateway; ignored with --test')
    args = parser.parse_args()
    if args.max_bytes <= 0:
        parser.error('--max-bytes must be positive')
    try:
        ipaddress.ip_address(args.bind_address)
    except ValueError:
        parser.error('--bind-address must be an IPv4 or IPv6 address')
    if not 1 <= args.http_port <= 65535:
        parser.error('--http-port must be between 1 and 65535')
    bind_address = '127.0.0.1' if args.test else args.bind_address
    http_port = 18082 if args.test else args.http_port
    destination = ROOT / ('config/compose-test.env' if args.test else 'config/compose.env')
    content = '\n'.join([
        'AR_DATABASE_PASSWORD=' + secrets.token_urlsafe(32),
        'AR_TOKEN_SECRET=' + secrets.token_urlsafe(64),
        'AR_BOOTSTRAP_PASSWORD=' + secrets.token_urlsafe(24),
        'AR_STORAGE_MAX_BYTES=' + str(args.max_bytes),
        'AR_BIND_ADDRESS=' + bind_address,
        'AR_HTTP_PORT=' + str(http_port),
        '',
    ])
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.error('Configuration already exists; refusing to replace credentials')
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(content)
    print('Created private configuration:', destination.relative_to(ROOT))
    print('No credentials printed. Open the private file locally for initial bootstrap login.')


if __name__ == '__main__':
    main()
