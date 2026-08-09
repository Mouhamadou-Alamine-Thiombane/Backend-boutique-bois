import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth import require_super_admin
from app.database import get_pool

router = APIRouter(prefix="/export", tags=["Export"])

# Tous les exports sont réservés au Super Admin : le cahier des charges
# exclut explicitement "Exporter des rapports" des droits du Vendeur.


def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ventes")
async def exporter_ventes(current_user: dict = Depends(require_super_admin)):
    """Export CSV (compatible Excel) de toutes les ventes de la boutique."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT v.numero_facture, v.date_vente, c.nom AS client, v.montant_total,
                   v.remise, v.montant_net, v.statut_paiement, v.mode_paiement,
                   v.avance, v.reste_a_payer
            FROM ventes v
            LEFT JOIN clients c ON c.id = v.client_id
            ORDER BY v.date_vente DESC
            """
        )
    return _csv_response([dict(r) for r in rows], "ventes.csv")


@router.get("/clients")
async def exporter_clients(current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT nom, prenom, telephone, type_client, plafond_credit, solde_actuel
            FROM clients
            ORDER BY nom
            """
        )
    return _csv_response([dict(r) for r in rows], "clients.csv")


@router.get("/fournisseurs")
async def exporter_fournisseurs(current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT nom, contact, telephone, adresse, email FROM fournisseurs ORDER BY nom"
        )
    return _csv_response([dict(r) for r in rows], "fournisseurs.csv")


@router.get("/dettes")
async def exporter_dettes(current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.nom, c.prenom, c.telephone, c.solde_actuel,
                   COUNT(v.id) FILTER (WHERE v.reste_a_payer > 0) AS ventes_impayees
            FROM clients c
            JOIN ventes v ON v.client_id = c.id
            WHERE c.solde_actuel > 0
            GROUP BY c.id, c.nom, c.prenom, c.telephone, c.solde_actuel
            ORDER BY c.solde_actuel DESC
            """
        )
    return _csv_response([dict(r) for r in rows], "dettes.csv")
