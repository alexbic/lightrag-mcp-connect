from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

import asyncpg

SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")


@dataclass(frozen=True)
class Principal:
    key_id: int
    workspace: str | None
    is_admin: bool


class WorkspaceRegistry:
    def __init__(self, pool: asyncpg.Pool, pepper: str):
        if len(pepper) < 32:
            raise ValueError("WORKSPACE_KEY_PEPPER must contain at least 32 characters")
        self.pool = pool
        self.pepper = pepper.encode()

    @classmethod
    async def connect(cls, dsn: str, pepper: str) -> "WorkspaceRegistry":
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        registry = cls(pool, pepper)
        await registry.initialize()
        return registry

    async def close(self) -> None:
        await self.pool.close()

    async def initialize(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lightrag_workspaces (
                    slug text PRIMARY KEY,
                    display_name text NOT NULL,
                    enabled boolean NOT NULL DEFAULT true,
                    created_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS lightrag_workspace_keys (
                    id bigserial PRIMARY KEY,
                    workspace_slug text REFERENCES lightrag_workspaces(slug),
                    key_hash text NOT NULL UNIQUE,
                    key_prefix text NOT NULL,
                    is_admin boolean NOT NULL DEFAULT false,
                    enabled boolean NOT NULL DEFAULT true,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    last_used_at timestamptz
                );
                CREATE INDEX IF NOT EXISTS lightrag_workspace_keys_prefix_idx
                    ON lightrag_workspace_keys(key_prefix);
                INSERT INTO lightrag_workspaces(slug, display_name)
                VALUES ('main', 'Main') ON CONFLICT (slug) DO NOTHING;
                """
            )

    def hash_key(self, key: str) -> str:
        return hmac.new(self.pepper, key.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def validate_slug(slug: str) -> str:
        normalized = slug.strip().lower()
        if not SLUG_RE.fullmatch(normalized):
            raise ValueError(
                "workspace must start with a letter and contain only lowercase "
                "letters, digits, '_' or '-' (maximum 63 characters)"
            )
        return normalized

    async def create_workspace(self, slug: str, display_name: str | None = None) -> str:
        slug = self.validate_slug(slug)
        async with self.pool.acquire() as conn:
            inserted = await conn.fetchval(
                """INSERT INTO lightrag_workspaces(slug, display_name)
                   VALUES ($1, $2) ON CONFLICT (slug) DO NOTHING
                   RETURNING slug""",
                slug,
                display_name or slug,
            )
        if inserted is None:
            raise ValueError(f"workspace already exists: {slug}")
        return slug

    async def workspace_enabled(self, slug: str) -> bool:
        return (
            await self.pool.fetchval(
                "SELECT enabled FROM lightrag_workspaces WHERE slug=$1", slug
            )
            is True
        )

    async def bootstrap_admin_key(self, token: str) -> None:
        """Idempotently import the operator's env key as a superadmin key.

        The env ``LIGHTRAG_API_KEY`` is the operator's master key. In gateway
        mode it is imported here as an admin principal (``is_admin=true``,
        unscoped to any single workspace) so it sees every workspace and
        unlocks the admin MCP tools. In simple mode the same key hits LightRAG
        directly and already sees all data — so toggling gateway mode never
        locks the operator out (architecture decision #3).
        """
        if not token:
            return
        await self.pool.execute(
            """INSERT INTO lightrag_workspace_keys
               (workspace_slug, key_hash, key_prefix, is_admin)
               VALUES (NULL, $1, $2, true)
               ON CONFLICT (key_hash) DO NOTHING""",
            self.hash_key(token),
            token[:18],
        )

    async def issue_key(self, workspace: str | None, *, admin: bool = False) -> str:
        if not admin:
            if workspace is None:
                raise ValueError("workspace is required for a non-admin key")
            workspace = self.validate_slug(workspace)
            exists = await self.pool.fetchval(
                "SELECT enabled FROM lightrag_workspaces WHERE slug=$1", workspace
            )
            if exists is not True:
                raise ValueError(f"workspace is unknown or disabled: {workspace}")
        label = "admin" if admin else workspace
        token = f"lr_{label}_{secrets.token_urlsafe(32)}"
        await self.pool.execute(
            """INSERT INTO lightrag_workspace_keys
               (workspace_slug, key_hash, key_prefix, is_admin)
               VALUES ($1, $2, $3, $4)""",
            None if admin else workspace,
            self.hash_key(token),
            token[:18],
            admin,
        )
        return token

    async def resolve(self, token: str) -> Principal | None:
        row = await self.pool.fetchrow(
            """SELECT k.id, k.workspace_slug, k.is_admin
               FROM lightrag_workspace_keys k
               LEFT JOIN lightrag_workspaces w ON w.slug=k.workspace_slug
               WHERE k.key_hash=$1 AND k.enabled
                 AND (k.is_admin OR w.enabled)""",
            self.hash_key(token),
        )
        if row is None:
            return None
        await self.pool.execute(
            "UPDATE lightrag_workspace_keys SET last_used_at=now() WHERE id=$1",
            row["id"],
        )
        return Principal(row["id"], row["workspace_slug"], row["is_admin"])

    async def list_workspaces(self) -> list[dict[str, object]]:
        rows = await self.pool.fetch(
            """SELECT w.slug, w.display_name, w.enabled, w.created_at,
                      count(k.id) FILTER (WHERE k.enabled) AS active_keys
               FROM lightrag_workspaces w
               LEFT JOIN lightrag_workspace_keys k ON k.workspace_slug=w.slug
               GROUP BY w.slug ORDER BY w.slug"""
        )
        return [dict(row) for row in rows]

    async def revoke_key(self, prefix: str) -> int:
        result = await self.pool.execute(
            "UPDATE lightrag_workspace_keys SET enabled=false WHERE key_prefix=$1",
            prefix,
        )
        return int(result.rsplit(" ", 1)[-1])
