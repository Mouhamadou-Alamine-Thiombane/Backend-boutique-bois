from fastapi import APIRouter, Depends, HTTPException

from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_pool
from app.schemas import LoginRequest, RefreshRequest, TokenResponse, UtilisateurOut

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, nom, prenom, email, telephone, role, actif, password_hash
            FROM utilisateurs
            WHERE email = $1
            """,
            payload.email,
        )

        if row is None or not verify_password(payload.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

        if not row["actif"]:
            raise HTTPException(status_code=403, detail="Compte désactivé, contactez l'administrateur")

        await conn.execute(
            "UPDATE utilisateurs SET derniere_connexion = now() WHERE id = $1",
            row["id"],
        )

    token_data = {"sub": str(row["id"]), "role": row["role"]}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UtilisateurOut(**dict(row)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest):
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token de rafraîchissement invalide")

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, nom, prenom, email, telephone, role, actif FROM utilisateurs WHERE id = $1",
            decoded["sub"],
        )
    if row is None or not row["actif"]:
        raise HTTPException(status_code=401, detail="Utilisateur invalide")

    token_data = {"sub": str(row["id"]), "role": row["role"]}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        user=UtilisateurOut(**dict(row)),
    )


@router.get("/me", response_model=UtilisateurOut)
async def me(current_user: dict = Depends(get_current_user)):
    return UtilisateurOut(**current_user)
