"""Run with docker compose exec web python -m app.web.cli create-admin admin."""
import argparse
import getpass
import sys

from app.common.config import Settings
from app.web.auth import set_admin
from app.web.database import Database


def main():
    parser = argparse.ArgumentParser(description='SSH Sentinel admin account')
    parser.add_argument('action', choices=['create-admin'])
    parser.add_argument('username')
    args = parser.parse_args()
    password = getpass.getpass('New dashboard password (at least 12 characters): ')
    if password != getpass.getpass('Repeat password: '):
        sys.exit('Passwords do not match')
    settings = Settings.from_env()
    try:
        set_admin(Database(settings.data_dir / 'sentinel.sqlite', settings.max_db_bytes), args.username, password)
    except ValueError as exc:
        sys.exit(str(exc))
    print('Admin saved. Existing sessions revoked.')


if __name__ == '__main__':
    main()
