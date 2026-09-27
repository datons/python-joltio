"""Joltio CLI — query data and manage authentication.

Usage:
    joltio auth set <KEY>     Save API key to ~/.config/joltio/config.toml
    joltio auth show          Show the saved key (masked)
    joltio auth remove        Remove the saved key
"""

from __future__ import annotations

import argparse
import json
import sys

from joltio.config import read_api_key, remove_api_key, write_api_key

def _data(args: argparse.Namespace) -> None:
    from joltio import Client
    with Client() as client:
        if args.data_command == 'query':
            result = client.data.query_raw(args.sql).model_dump()
        elif args.data_command == 'coverage':
            result = client.data.coverage(args.table)
        elif args.data_command == 'search':
            result = client.data.search(args.query).model_dump()
        else:
            result = client.data.metadata().model_dump()
        print(json.dumps(result, default=str))


def _auth_set(args: argparse.Namespace) -> None:
    write_api_key(args.key)
    masked = args.key[:8] + "..." + args.key[-4:] if len(args.key) > 12 else args.key[:4] + "..."
    print(f"API key saved: {masked}")


def _auth_show(_args: argparse.Namespace) -> None:
    key = read_api_key()
    if not key:
        print("No API key configured.")
        print("Set one with: joltio auth set <KEY>")
        sys.exit(1)
    masked = key[:8] + "..." + key[-4:] if len(key) > 12 else key[:4] + "..."
    print(f"API key: {masked}")


def _auth_remove(_args: argparse.Namespace) -> None:
    if remove_api_key():
        print("API key removed.")
    else:
        print("No API key to remove.")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="joltio",
        description="Joltio Data CLI",
    )
    subparsers = parser.add_subparsers(dest="command")

    data_parser = subparsers.add_parser('data', help='Query Joltio Data')
    data_sub = data_parser.add_subparsers(dest='data_command', required=True)
    query = data_sub.add_parser('query')
    query.add_argument('sql')
    query.set_defaults(func=_data)
    search = data_sub.add_parser('search')
    search.add_argument('query')
    search.set_defaults(func=_data)
    coverage = data_sub.add_parser('coverage')
    coverage.add_argument('--table')
    coverage.set_defaults(func=_data)
    metadata = data_sub.add_parser('metadata')
    metadata.set_defaults(func=_data)

    # joltio auth
    auth_parser = subparsers.add_parser("auth", help="Manage API key authentication")
    auth_sub = auth_parser.add_subparsers(dest="auth_command")

    # joltio auth set <KEY>
    set_parser = auth_sub.add_parser("set", help="Save API key")
    set_parser.add_argument("key", help="Your Joltio API key")
    set_parser.set_defaults(func=_auth_set)

    # joltio auth show
    show_parser = auth_sub.add_parser("show", help="Show saved API key (masked)")
    show_parser.set_defaults(func=_auth_show)

    # joltio auth remove
    remove_parser = auth_sub.add_parser("remove", help="Remove saved API key")
    remove_parser.set_defaults(func=_auth_remove)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "auth" and not args.auth_command:
        auth_parser.print_help()
        sys.exit(0)

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
