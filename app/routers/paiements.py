from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_any_role
from app.database import get_pool
from app.schemas import PaiementCreate, PaiementOut

router = APIRouter(prefix="/paiements", tags=["Paiements"])


@router.post("", response_model=PaiementOut, status_code=201)
async def enregistrer_paiement(payload: PaiementCreate, current_user: dict = Depends(require_any_role)):
    """Enregistre un paiement (total ou partiel) sur une dette existante.
    Met à jour le reste à payer de la vente, son statut, et le solde du
    client — conformément au diagramme de séquence 4.3."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            vente = await conn.fetchrow("SELECT * FROM ventes WHERE id = $1", payload.vente_id)
            if vente is None:
                raise HTTPException(status_code=404, detail="Vente introuvable")
            if vente["reste_a_payer"] <= 0:
                raise HTTPException(status_code=400, detail="Cette vente est déjà entièrement payée")
            if payload.montant > vente["reste_a_payer"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Le paiement ({payload.montant}) dépasse le reste à payer ({vente['reste_a_payer']})",
                )

            paiement_row = await conn.fetchrow(
                """
                INSERT INTO paiements (vente_id, montant, mode_paiement, reference, encaisse_par)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                payload.vente_id,
                payload.montant,
                payload.mode_paiement,
                payload.reference,
                current_user["id"],
            )

            nouveau_reste = vente["reste_a_payer"] - payload.montant
            nouveau_statut = "PAYE" if nouveau_reste == 0 else "PARTIEL"

            await conn.execute(
                """
                UPDATE ventes SET reste_a_payer = $2, avance = avance + $3, statut_paiement = $4,
                                   updated_at = now()
                WHERE id = $1
                """,
                payload.vente_id,
                nouveau_reste,
                payload.montant,
                nouveau_statut,
            )

            if vente["client_id"] is not None:
                await conn.execute(
                    "UPDATE clients SET solde_actuel = solde_actuel - $2, updated_at = now() WHERE id = $1",
                    vente["client_id"],
                    payload.montant,
                )

    return PaiementOut(**dict(paiement_row))


@router.get("/vente/{vente_id}", response_model=list[PaiementOut])
async def historique_paiements_vente(vente_id, current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM paiements WHERE vente_id = $1 ORDER BY date_paiement DESC", vente_id
        )
    return [PaiementOut(**dict(r)) for r in rows]
