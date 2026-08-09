"""
Authentification JWT + gestion des rôles (SUPER_ADMIN / VENDEUR).
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.database import get_pool

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Type de token invalide")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token invalide")

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, nom, prenom, email, telephone, role, actif
            FROM utilisateurs
            WHERE id = $1
            """,
            user_id,
        )

    if row is None:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    if not row["actif"]:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    return dict(row)


def require_role(*allowed_roles: str):
    """Dependency factory: restreint une route à un ou plusieurs rôles."""

    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Accès refusé. Rôle requis: {', '.join(allowed_roles)}, "
                    f"votre rôle: {user['role']}"
                ),
            )
        return user

    return role_checker


require_super_admin = require_role("SUPER_ADMIN")
require_any_role = require_role("SUPER_ADMIN", "VENDEUR")
