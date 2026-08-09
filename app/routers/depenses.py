from datetime import date

from fastapi import APIRouter, Depends

from app.auth import require_super_admin
from app.database import get_pool
from app.schemas import DepenseCreate, DepenseOut

router = APIRouter(prefix="/depenses", tags=["Dépenses"])


@router.get("", response_model=list[DepenseOut])
async def lister_depenses(
    date_debut: date | None = None,
    date_fin: date | None = None,
    current_user: dict = Depends(require_super_admin),
):
    conditions = []
    params: list = []
    if date_debut is not None:
        params.append(date_debut)
        conditions.append(f"date_depense >= ${len(params)}")
    if date_fin is not None:
        params.append(date_fin)
        conditions.append(f"date_depense <= ${len(params)}")

    query = "SELECT * FROM depenses"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY date_depense DESC"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [DepenseOut(**dict(r)) for r in rows]


@router.post("", response_model=DepenseOut, status_code=201)
async def creer_depense(payload: DepenseCreate, current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO depenses (libelle, categorie, montant, date_depense, commentaire, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            payload.libelle,
            payload.categorie,
            payload.montant,
            payload.date_depense,
            payload.commentaire,
            current_user["id"],
        )
    return DepenseOut(**dict(row))


@router.get("/par-categorie")
async def total_par_categorie(
    date_debut: date | None = None,
    date_fin: date | None = None,
    current_user: dict = Depends(require_super_admin),
):
    conditions = []
    params: list = []
    if date_debut is not None:
        params.append(date_debut)
        conditions.append(f"date_depense >= ${len(params)}")
    if date_fin is not None:
        params.append(date_fin)
        conditions.append(f"date_depense <= ${len(params)}")

    query = "SELECT categorie, SUM(montant) AS total FROM depenses"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " GROUP BY categorie ORDER BY total DESC"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]
