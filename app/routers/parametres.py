from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_super_admin
from app.database import get_pool
from app.schemas import ParametreOut, ParametreUpdate

router = APIRouter(prefix="/parametres", tags=["Paramètres"])


@router.get("", response_model=list[ParametreOut])
async def lister_parametres(current_user: dict = Depends(get_current_user)):
    """Tous les utilisateurs peuvent lire les paramètres (ex: devise,
    seuils par défaut) mais seul le Super Admin peut les modifier."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM parametres_app ORDER BY cle")
    return [ParametreOut(**dict(r)) for r in rows]


@router.put("/{cle}", response_model=ParametreOut)
async def modifier_parametre(
    cle: str, payload: ParametreUpdate, current_user: dict = Depends(require_super_admin)
):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE parametres_app SET valeur = $2, updated_at = now() WHERE cle = $1 RETURNING *",
            cle,
            payload.valeur,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Paramètre introuvable")
    return ParametreOut(**dict(row))
