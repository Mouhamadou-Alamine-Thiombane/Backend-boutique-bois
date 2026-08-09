"""
Gestion du pool de connexions PostgreSQL (asyncpg), pointant vers la base
Supabase du projet. On utilise asyncpg directement (plutôt que le SDK
Supabase) pour profiter des transactions, des vues et fonctions SQL créées
dans database/schema.sql.
"""
import asyncpg
from app.config import settings

_pool: asyncpg.Pool | None = None


async def connect_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30,
        statement_cache_size=0,
    )


async def disconnect_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Le pool de base de données n'est pas initialisé.")
    return _pool
