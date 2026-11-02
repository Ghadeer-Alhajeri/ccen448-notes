"""Generate unique lab secrets locally without printing or overwriting them."""
import os
import secrets

try:
    fd = os.open('.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('.env already exists; kept your existing settings and secrets.')
else:
    with os.fdopen(fd, 'w') as file:
        file.write(f'SECRET_KEY={secrets.token_hex(32)}\n')
        file.write(f'POSTGRES_PASSWORD={secrets.token_hex(24)}\n')
        file.write('COOKIE_SECURE=false\nWEB_BIND=0.0.0.0\n')
    print('Created .env with unique secrets. Keep this file private.')
