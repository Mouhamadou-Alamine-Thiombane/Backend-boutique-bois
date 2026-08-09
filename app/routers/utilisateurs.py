from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import hash_password, require_super_admin
from app.database import get_pool
from app.schemas import UtilisateurCreate, UtilisateurOut

router = APIRouter(prefix="/utilisateurs", tags=["Utilisateurs"])


@router.get("", response_model=list[UtilisateurOut])
async def lister_utilisateurs(current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, nom, prenom, email, telephone, role, actif FROM utilisateurs ORDER BY nom"
        )
    return [UtilisateurOut(**dict(r)) for r in rows]


@router.post("", response_model=UtilisateurOut, status_code=201)
async def creer_utilisateur(
    payload: UtilisateurCreate, current_user: dict = Depends(require_super_admin)
):
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT id FROM utilisateurs WHERE email = $1", payload.email)
        if existing:
            raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")

        row = await conn.fetchrow(
            """
            INSERT INTO utilisateurs (nom, prenom, email, password_hash, telephone, role)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, nom, prenom, email, telephone, role, actif
            """,
            payload.nom,
            payload.prenom,
            payload.email,
            hash_password(payload.password),
            payload.telephone,
            payload.role,
        )
    return UtilisateurOut(**dict(row))


@router.patch("/{utilisateur_id}/desactiver", response_model=UtilisateurOut)
async def desactiver_utilisateur(
    utilisateur_id: UUID, current_user: dict = Depends(require_super_admin)
):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE utilisateurs SET actif = FALSE, updated_at = now()
            WHERE id = $1
            RETURNING id, nom, prenom, email, telephone, role, actif
            """,
            utilisateur_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return UtilisateurOut(**dict(row))


@router.patch("/{utilisateur_id}/reactiver", response_model=UtilisateurOut)
async def reactiver_utilisateur(
    utilisateur_id: UUID, current_user: dict = Depends(require_super_admin)
):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE utilisateurs SET actif = TRUE, updated_at = now()
            WHERE id = $1
            RETURNING id, nom, prenom, email, telephone, role, actif
            """,
            utilisateur_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return UtilisateurOut(**dict(row))
