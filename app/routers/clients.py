from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_any_role
from app.database import get_pool
from app.schemas import ClientCreate, ClientOut, ClientUpdate

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.get("", response_model=list[ClientOut])
async def lister_clients(
    recherche: str | None = None,
    dettes_seulement: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Liste des clients actifs. Un VENDEUR ne voit que les clients qu'il a
    créés ou auxquels il a déjà vendu ; le SUPER_ADMIN voit tous les
    clients de la boutique. Les clients archivés (supprimés) n'apparaissent
    jamais ici."""
    conditions = ["actif = TRUE"]
    params: list = []
    if current_user["role"] == "VENDEUR":
        params.append(current_user["id"])
        conditions.append(
            f"(created_by = ${len(params)} OR EXISTS "
            f"(SELECT 1 FROM ventes v WHERE v.client_id = clients.id AND v.vendeur_id = ${len(params)}))"
        )
    if recherche:
        params.append(f"%{recherche}%")
        conditions.append(f"(nom ILIKE ${len(params)} OR prenom ILIKE ${len(params)} OR telephone ILIKE ${len(params)})")
    if dettes_seulement:
        conditions.append("solde_actuel > 0")

    query = "SELECT * FROM clients WHERE " + " AND ".join(conditions) + " ORDER BY nom"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [ClientOut(**dict(r)) for r in rows]


@router.get("/{client_id}", response_model=ClientOut)
async def obtenir_client(client_id: UUID, current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM clients WHERE id = $1", client_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return ClientOut(**dict(row))


@router.post("", response_model=ClientOut, status_code=201)
async def creer_client(payload: ClientCreate, current_user: dict = Depends(require_any_role)):
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM clients WHERE telephone = $1 AND actif = TRUE", payload.telephone
        )
        if existing:
            raise HTTPException(status_code=409, detail="Un client avec ce téléphone existe déjà")

        row = await conn.fetchrow(
            """
            INSERT INTO clients (nom, prenom, telephone, adresse, email, type_client,
                                  code_contribuable, plafond_credit, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            payload.nom,
            payload.prenom,
            payload.telephone,
            payload.adresse,
            payload.email,
            payload.type_client,
            payload.code_contribuable,
            payload.plafond_credit,
            current_user["id"],
        )
    return ClientOut(**dict(row))


@router.put("/{client_id}", response_model=ClientOut)
async def modifier_client(
    client_id: UUID, payload: ClientUpdate, current_user: dict = Depends(require_any_role)
):
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")

    set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(fields))
    values = list(fields.values())

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE clients SET {set_clause}, updated_at = now() WHERE id = $1 RETURNING *",
            client_id,
            *values,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return ClientOut(**dict(row))


@router.delete("/{client_id}", status_code=204)
async def supprimer_client(client_id: UUID, current_user: dict = Depends(require_any_role)):
    """Supprime un client. S'il a déjà des ventes enregistrées, il est
    archivé (masqué des listes) plutôt que supprimé physiquement, pour
    préserver l'historique comptable de ses ventes passées. Un client
    sans aucune vente est supprimé définitivement."""
    pool = get_pool()
    async with pool.acquire() as conn:
        client = await conn.fetchrow("SELECT id FROM clients WHERE id = $1", client_id)
        if client is None:
            raise HTTPException(status_code=404, detail="Client introuvable")

        a_des_ventes = await conn.fetchval("SELECT 1 FROM ventes WHERE client_id = $1 LIMIT 1", client_id)
        if a_des_ventes:
            await conn.execute(
                "UPDATE clients SET actif = FALSE, updated_at = now() WHERE id = $1", client_id
            )
        else:
            await conn.execute("DELETE FROM clients WHERE id = $1", client_id)


@router.get("/{client_id}/historique-ventes")
async def historique_achats_client(client_id: UUID, current_user: dict = Depends(get_current_user)):
    """Historique des achats du client (section 3.2 gestion des clients)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, numero_facture, date_vente, montant_net, statut_paiement, reste_a_payer
            FROM ventes
            WHERE client_id = $1
            ORDER BY date_vente DESC
            """,
            client_id,
        )
    return [dict(r) for r in rows]