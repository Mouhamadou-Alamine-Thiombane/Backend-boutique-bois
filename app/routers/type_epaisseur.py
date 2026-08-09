from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_super_admin
from app.database import get_pool
from app.schemas import TypeEpaisseurCreate, TypeEpaisseurOut

router = APIRouter(prefix="/type-epaisseur", tags=["Types d'épaisseur"])


@router.get("", response_model=list[TypeEpaisseurOut])
async def lister_types(current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM type_epaisseur ORDER BY ordre_affichage")
    return [TypeEpaisseurOut(**dict(r)) for r in rows]


@router.post("", response_model=TypeEpaisseurOut, status_code=201)
async def creer_type_epaisseur(
    payload: TypeEpaisseurCreate, current_user: dict = Depends(require_super_admin)
):
    """Permet d'ajouter un nouveau type d'épaisseur (ex: '5T' à 15mm) sans
    toucher au code, comme demandé dans le cahier des charges (section 3.1.3)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM type_epaisseur WHERE designation = $1", payload.designation
        )
        if existing:
            raise HTTPException(status_code=409, detail="Ce type d'épaisseur existe déjà")

        row = await conn.fetchrow(
            """
            INSERT INTO type_epaisseur (designation, epaisseur_mm, ordre_affichage)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            payload.designation,
            payload.epaisseur_mm,
            payload.ordre_affichage,
        )
    return TypeEpaisseurOut(**dict(row))


@router.delete("/{type_id}", status_code=204)
async def supprimer_type_epaisseur(
    type_id: UUID, current_user: dict = Depends(require_super_admin)
):
    pool = get_pool()
    async with pool.acquire() as conn:
        in_use = await conn.fetchval(
            "SELECT id FROM tarif_bois WHERE type_epaisseur_id = $1 LIMIT 1", type_id
        )
        if in_use:
            raise HTTPException(
                status_code=409,
                detail="Impossible de supprimer: ce type est utilisé par des tarifs existants",
            )
        result = await conn.execute("DELETE FROM type_epaisseur WHERE id = $1", type_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Type d'épaisseur introuvable")
