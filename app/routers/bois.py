from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_super_admin
from app.database import get_pool
from app.schemas import BoisCreate, BoisOut, BoisUpdate

router = APIRouter(prefix="/bois", tags=["Bois"])


@router.get("", response_model=list[BoisOut])
async def lister_bois(actif: bool | None = None, current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    query = "SELECT * FROM bois"
    params = []
    if actif is not None:
        query += " WHERE actif = $1"
        params.append(actif)
    query += " ORDER BY nom"
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [BoisOut(**dict(r)) for r in rows]


@router.get("/{bois_id}", response_model=BoisOut)
async def obtenir_bois(bois_id: UUID, current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM bois WHERE id = $1", bois_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Bois introuvable")
    return BoisOut(**dict(row))


@router.post("", response_model=BoisOut, status_code=201)
async def creer_bois(payload: BoisCreate, current_user: dict = Depends(require_super_admin)):
    """Ajoute un nouveau type de bois (ex: 'Dabemol'). Aucune modification
    de code n'est nécessaire — c'est la flexibilité demandée dans le cahier
    des charges."""
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT id FROM bois WHERE nom = $1", payload.nom)
        if existing:
            raise HTTPException(status_code=409, detail="Ce bois existe déjà")

        row = await conn.fetchrow(
            """
            INSERT INTO bois (nom, categorie, unite, seuil_alerte, image_url, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            payload.nom,
            payload.categorie,
            payload.unite,
            payload.seuil_alerte,
            payload.image_url,
            current_user["id"],
        )
    return BoisOut(**dict(row))


@router.put("/{bois_id}", response_model=BoisOut)
async def modifier_bois(
    bois_id: UUID, payload: BoisUpdate, current_user: dict = Depends(require_super_admin)
):
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")

    set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(fields))
    values = list(fields.values())

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE bois SET {set_clause}, updated_at = now() WHERE id = $1 RETURNING *",
            bois_id,
            *values,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Bois introuvable")
    return BoisOut(**dict(row))


@router.patch("/{bois_id}/desactiver", status_code=204)
async def desactiver_bois(bois_id: UUID, current_user: dict = Depends(require_super_admin)):
    """Désactive un bois (soft delete) plutôt que de le supprimer, pour
    préserver l'historique des ventes qui le référencent. C'est l'option
    recommandée pour un bois déjà vendu."""
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE bois SET actif = FALSE, updated_at = now() WHERE id = $1", bois_id
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Bois introuvable")


@router.delete("/{bois_id}", status_code=204)
async def supprimer_bois(bois_id: UUID, current_user: dict = Depends(require_super_admin)):
    """Supprime définitivement un bois. Refusé s'il est référencé par des
    tarifs, du stock ou des ventes existantes — utilisez /desactiver dans
    ce cas pour conserver l'historique."""
    pool = get_pool()
    async with pool.acquire() as conn:
        en_usage = await conn.fetchval(
            """
            SELECT 1 WHERE EXISTS (SELECT 1 FROM tarif_bois WHERE bois_id = $1)
               OR EXISTS (SELECT 1 FROM ligne_vente WHERE bois_id = $1)
               OR EXISTS (SELECT 1 FROM stock WHERE bois_id = $1 AND quantite > 0)
            """,
            bois_id,
        )
        if en_usage:
            raise HTTPException(
                status_code=409,
                detail="Ce bois est déjà utilisé (tarifs, ventes ou stock). Désactivez-le plutôt que de le supprimer.",
            )
        result = await conn.execute("DELETE FROM bois WHERE id = $1", bois_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Bois introuvable")
