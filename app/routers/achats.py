from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_super_admin
from app.database import get_pool
from app.schemas import (
    AchatCreate,
    AchatOut,
    FournisseurCreate,
    FournisseurOut,
)

router = APIRouter(tags=["Fournisseurs & Achats"])


@router.get("/fournisseurs", response_model=list[FournisseurOut])
async def lister_fournisseurs(current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM fournisseurs ORDER BY nom")
    return [FournisseurOut(**dict(r)) for r in rows]


@router.post("/fournisseurs", response_model=FournisseurOut, status_code=201)
async def creer_fournisseur(payload: FournisseurCreate, current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO fournisseurs (nom, contact, telephone, adresse, email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            payload.nom,
            payload.contact,
            payload.telephone,
            payload.adresse,
            payload.email,
        )
    return FournisseurOut(**dict(row))


@router.post("/achats", response_model=AchatOut, status_code=201)
async def enregistrer_achat(payload: AchatCreate, current_user: dict = Depends(require_super_admin)):
    """Enregistre un achat de bois auprès d'un fournisseur, comme une
    simple dépense : quantité × prix unitaire par ligne. Aucun suivi de
    stock n'est effectué (retiré à la demande du gérant)."""
    if not payload.lignes:
        raise HTTPException(status_code=400, detail="L'achat doit contenir au moins une ligne")

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            montant_total = 0
            lignes_calculees = []

            for ligne in payload.lignes:
                bois = await conn.fetchval("SELECT id FROM bois WHERE id = $1", ligne.bois_id)
                if bois is None:
                    raise HTTPException(status_code=404, detail=f"Bois introuvable ({ligne.bois_id})")

                sous_total = round(ligne.prix_unitaire_achat * ligne.quantite)
                montant_total += sous_total
                lignes_calculees.append(
                    {
                        "bois_id": ligne.bois_id,
                        "type_epaisseur_id": ligne.type_epaisseur_id,
                        "quantite": ligne.quantite,
                        "prix_unitaire_achat": ligne.prix_unitaire_achat,
                        "sous_total": sous_total,
                    }
                )

            achat_id = await conn.fetchval(
                """
                INSERT INTO achats (fournisseur_id, montant_total, statut, commentaire, created_by)
                VALUES ($1, $2, 'PAYE', $3, $4)
                RETURNING id
                """,
                payload.fournisseur_id,
                montant_total,
                payload.commentaire,
                current_user["id"],
            )

            for lc in lignes_calculees:
                await conn.execute(
                    """
                    INSERT INTO ligne_achat (achat_id, bois_id, type_epaisseur_id, quantite,
                                              prix_unitaire_achat, sous_total)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    achat_id,
                    lc["bois_id"],
                    lc["type_epaisseur_id"],
                    lc["quantite"],
                    lc["prix_unitaire_achat"],
                    lc["sous_total"],
                )

            row = await conn.fetchrow("SELECT * FROM achats WHERE id = $1", achat_id)
    return AchatOut(**dict(row))


@router.get("/achats", response_model=list[AchatOut])
async def lister_achats(current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM achats ORDER BY date_achat DESC LIMIT 200")
    return [AchatOut(**dict(r)) for r in rows]