from __future__ import annotations

import argparse
import json
import os

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(prog="lightrag-workspace")
    parser.add_argument(
        "--url", default=os.getenv("WORKSPACE_GATEWAY_URL", "http://localhost:9621")
    )
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("name")
    create.add_argument("--display-name")
    sub.add_parser("list")
    add_key = sub.add_parser("key-add")
    add_key.add_argument("workspace")
    revoke = sub.add_parser("key-revoke")
    revoke.add_argument("prefix")
    sub.add_parser("admin-key-add")
    args = parser.parse_args()
    admin_key = os.environ.get("LIGHTRAG_ADMIN_KEY")
    if not admin_key:
        parser.error("LIGHTRAG_ADMIN_KEY is required")
    headers = {"X-Admin-Key": admin_key}
    with httpx.Client(base_url=args.url, headers=headers, timeout=30) as client:
        if args.command == "create":
            response = client.post(
                f"/_workspaces/{args.name}",
                json={"display_name": args.display_name} if args.display_name else {},
            )
        elif args.command == "list":
            response = client.get("/_workspaces")
        elif args.command == "key-add":
            response = client.post(f"/_workspaces/{args.workspace}/keys")
        elif args.command == "admin-key-add":
            response = client.post("/_keys/admin")
        else:
            response = client.delete(f"/_keys/{args.prefix}")
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2, default=str))
