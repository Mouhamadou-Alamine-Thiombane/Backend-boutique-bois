# from uuid import UUID

# from fastapi import APIRouter, Depends, HTTPException

# from app.auth import get_current_user
# from app.database import get_pool
# from app.schemas import (
#     PaiementClientCreate,
#     PaiementClientResult,
#     PaiementHistoriqueOut,
#     RelanceCreate,
#     RelanceOut,
#     TendanceDettes,
# )

# router = APIRouter(prefix="/dettes", tags=["Dettes"])


# @router.get("")
# async def lister_dettes(current_user: dict = Depends(get_current_user)):
#     """Liste des clients ayant une dette, avec l'ancienneté de la dette
#     (jours écoulés depuis la plus ancienne vente impayée) et le montant
#     initialement dû, pour permettre le classement par urgence
#     (Urgent > 30j, Moyen 15-30j, Récent < 15j) et l'affichage d'une jauge
#     de remboursement côté application. Un VENDEUR ne voit que les dettes
#     de ses propres clients/ventes."""
#     condition_role = ""
#     params: list = []
#     if current_user["role"] == "VENDEUR":
#         params.append(current_user["id"])
#         condition_role = f" AND v.vendeur_id = ${len(params)}"

#     pool = get_pool()
#     async with pool.acquire() as conn:
#         rows = await conn.fetch(
#             f"""
#             SELECT c.id AS client_id, c.nom, c.prenom, c.telephone, c.solde_actuel,
#                    COUNT(v.id) FILTER (WHERE v.reste_a_payer > 0) AS nombre_ventes_impayees,
#                    MIN(v.date_echeance) FILTER (WHERE v.reste_a_payer > 0) AS prochaine_echeance,
#                    (MIN(v.date_vente) FILTER (WHERE v.reste_a_payer > 0))::date AS date_plus_ancienne,
#                    COALESCE(CURRENT_DATE - (MIN(v.date_vente) FILTER (WHERE v.reste_a_payer > 0))::date, 0) AS jours_ecoules,
#                    COALESCE(SUM(v.montant_net) FILTER (WHERE v.reste_a_payer > 0), 0) AS montant_initial
#             FROM clients c
#             JOIN ventes v ON v.client_id = c.id
#             WHERE c.solde_actuel > 0 {condition_role}
#             GROUP BY c.id, c.nom, c.prenom, c.telephone, c.solde_actuel
#             ORDER BY c.solde_actuel DESC
#             """,
#             *params,
#         )
#     return [dict(r) for r in rows]


# @router.get("/tendance", response_model=TendanceDettes)
# async def tendance_dettes(current_user: dict = Depends(get_current_user)):
#     """Résumé pour l'en-tête de l'écran des dettes : total actuel et
#     comparaison du volume de nouvelles dettes générées ce mois-ci par
#     rapport au mois précédent (indicateur de tendance ↑/↓)."""
#     condition_role = ""
#     params: list = []
#     if current_user["role"] == "VENDEUR":
#         params.append(current_user["id"])
#         condition_role = f" AND vendeur_id = ${len(params)}"

#     pool = get_pool()
#     async with pool.acquire() as conn:
#         if current_user["role"] == "VENDEUR":
#             total_actuel = await conn.fetchval(
#                 "SELECT COALESCE(SUM(reste_a_payer), 0) FROM ventes WHERE reste_a_payer > 0 AND vendeur_id = $1",
#                 current_user["id"],
#             )
#             nb_clients = await conn.fetchval(
#                 """
#                 SELECT COUNT(DISTINCT client_id) FROM ventes
#                 WHERE reste_a_payer > 0 AND client_id IS NOT NULL AND vendeur_id = $1
#                 """,
#                 current_user["id"],
#             )
#         else:
#             total_actuel = await conn.fetchval("SELECT COALESCE(SUM(solde_actuel), 0) FROM clients")
#             nb_clients = await conn.fetchval("SELECT COUNT(*) FROM clients WHERE solde_actuel > 0")

#         mois_courant = await conn.fetchval(
#             f"""
#             SELECT COALESCE(SUM(reste_a_payer), 0) FROM ventes
#             WHERE reste_a_payer > 0
#               AND date_trunc('month', date_vente) = date_trunc('month', CURRENT_DATE)
#               {condition_role}
#             """,
#             *params,
#         )
#         mois_precedent = await conn.fetchval(
#             f"""
#             SELECT COALESCE(SUM(reste_a_payer), 0) FROM ventes
#             WHERE reste_a_payer > 0
#               AND date_trunc('month', date_vente) = date_trunc('month', CURRENT_DATE - INTERVAL '1 month')
#               {condition_role}
#             """,
#             *params,
#         )

#     if mois_precedent > 0:
#         variation = ((mois_courant - mois_precedent) / mois_precedent) * 100
#     elif mois_courant > 0:
#         variation = 100.0
#     else:
#         variation = 0.0

#     return TendanceDettes(
#         total_actuel=total_actuel,
#         nouvelles_dettes_mois_courant=mois_courant,
#         nouvelles_dettes_mois_precedent=mois_precedent,
#         variation_pourcentage=round(variation, 1),
#         nombre_clients_debiteurs=nb_clients,
#     )


# @router.get("/en-retard")
# async def dettes_en_retard(current_user: dict = Depends(get_current_user)):
#     """Ventes dont la date d'échéance est dépassée et qui ne sont pas soldées —
#     utile pour la fonctionnalité 'Relancer les clients débiteurs'."""
#     condition_role = ""
#     params: list = []
#     if current_user["role"] == "VENDEUR":
#         params.append(current_user["id"])
#         condition_role = f" AND v.vendeur_id = ${len(params)}"

#     pool = get_pool()
#     async with pool.acquire() as conn:
#         rows = await conn.fetch(
#             f"""
#             SELECT v.id, v.numero_facture, v.date_vente, v.date_echeance, v.reste_a_payer,
#                    c.id AS client_id, c.nom, c.prenom, c.telephone
#             FROM ventes v
#             JOIN clients c ON c.id = v.client_id
#             WHERE v.reste_a_payer > 0 AND v.date_echeance IS NOT NULL
#               AND v.date_echeance < CURRENT_DATE {condition_role}
#             ORDER BY v.date_echeance ASC
#             """,
#             *params,
#         )
#     return [dict(r) for r in rows]


# @router.post("/{client_id}/payer", response_model=PaiementClientResult, status_code=201)
# async def payer_dette_client(
#     client_id: UUID, payload: PaiementClientCreate, current_user: dict = Depends(get_current_user)
# ):
#     """Encaisse un paiement pour un client débiteur, réparti automatiquement
#     sur ses ventes impayées en commençant par les plus anciennes (FIFO).
#     C'est ce qui alimente l'écran d'encaissement : le vendeur saisit un
#     montant global (jusqu'à 'Tout payer') sans avoir à choisir une facture
#     précise. Un VENDEUR ne peut encaisser que sur ses propres ventes."""
#     pool = get_pool()
#     async with pool.acquire() as conn:
#         async with conn.transaction():
#             condition_role = ""
#             params: list = [client_id]
#             if current_user["role"] == "VENDEUR":
#                 params.append(current_user["id"])
#                 condition_role = f"AND vendeur_id = ${len(params)}"

#             ventes_ouvertes = await conn.fetch(
#                 f"""
#                 SELECT id, reste_a_payer FROM ventes
#                 WHERE client_id = $1 AND reste_a_payer > 0 {condition_role}
#                 ORDER BY date_vente ASC
#                 FOR UPDATE
#                 """,
#                 *params,
#             )

#             if not ventes_ouvertes:
#                 raise HTTPException(status_code=404, detail="Aucune dette trouvée pour ce client")

#             total_du = sum(v["reste_a_payer"] for v in ventes_ouvertes)
#             if payload.montant > total_du:
#                 raise HTTPException(
#                     status_code=400,
#                     detail=f"Le montant ({payload.montant}) dépasse la dette totale ({total_du})",
#                 )

#             restant = payload.montant
#             ventes_soldees = 0
#             ventes_mises_a_jour = 0

#             for vente in ventes_ouvertes:
#                 if restant <= 0:
#                     break
#                 part = min(restant, vente["reste_a_payer"])
#                 nouveau_reste = vente["reste_a_payer"] - part
#                 nouveau_statut = "PAYE" if nouveau_reste == 0 else "PARTIEL"

#                 await conn.execute(
#                     """
#                     INSERT INTO paiements (vente_id, montant, mode_paiement, reference, encaisse_par)
#                     VALUES ($1, $2, $3, $4, $5)
#                     """,
#                     vente["id"],
#                     part,
#                     payload.mode_paiement,
#                     payload.reference,
#                     current_user["id"],
#                 )
#                 await conn.execute(
#                     """
#                     UPDATE ventes SET reste_a_payer = $2, avance = avance + $3, statut_paiement = $4,
#                                        updated_at = now()
#                     WHERE id = $1
#                     """,
#                     vente["id"],
#                     nouveau_reste,
#                     part,
#                     nouveau_statut,
#                 )
#                 if nouveau_reste == 0:
#                     ventes_soldees += 1
#                 ventes_mises_a_jour += 1
#                 restant -= part

#             row = await conn.fetchrow(
#                 """
#                 UPDATE clients SET solde_actuel = solde_actuel - $2, updated_at = now()
#                 WHERE id = $1
#                 RETURNING solde_actuel
#                 """,
#                 client_id,
#                 payload.montant,
#             )

#     return PaiementClientResult(
#         montant_paye=payload.montant,
#         nouveau_solde=row["solde_actuel"],
#         ventes_soldees=ventes_soldees,
#         ventes_mises_a_jour=ventes_mises_a_jour,
#     )


# @router.get("/{client_id}/paiements", response_model=list[PaiementHistoriqueOut])
# async def historique_paiements_client(client_id: UUID, current_user: dict = Depends(get_current_user)):
#     """Historique chronologique de tous les paiements reçus d'un client,
#     toutes ventes confondues — alimente la timeline de l'écran client."""
#     condition_role = ""
#     params: list = [client_id]
#     if current_user["role"] == "VENDEUR":
#         params.append(current_user["id"])
#         condition_role = f"AND v.vendeur_id = ${len(params)}"

#     pool = get_pool()
#     async with pool.acquire() as conn:
#         rows = await conn.fetch(
#             f"""
#             SELECT p.id, p.vente_id, v.numero_facture, p.montant, p.mode_paiement,
#                    p.date_paiement, p.reference
#             FROM paiements p
#             JOIN ventes v ON v.id = p.vente_id
#             WHERE v.client_id = $1 {condition_role}
#             ORDER BY p.date_paiement DESC
#             """,
#             *params,
#         )
#     return [PaiementHistoriqueOut(**dict(r)) for r in rows]


# @router.post("/{client_id}/relancer", response_model=RelanceOut, status_code=201)
# async def relancer_client(
#     client_id: UUID, payload: RelanceCreate, current_user: dict = Depends(get_current_user)
# ):
#     """Enregistre une relance envoyée à un client débiteur (section
#     'Relancer les clients débiteurs'). Le canal EMAIL/SMS est journalisé
#     ici ; l'envoi effectif nécessite de brancher un fournisseur d'email/SMS
#     (ex: SendGrid, Twilio) dans un prochain incrément."""
#     pool = get_pool()
#     async with pool.acquire() as conn:
#         client = await conn.fetchrow("SELECT id, solde_actuel FROM clients WHERE id = $1", client_id)
#         if client is None:
#             raise HTTPException(status_code=404, detail="Client introuvable")
#         if client["solde_actuel"] <= 0:
#             raise HTTPException(status_code=400, detail="Ce client n'a pas de dette en cours")

#         row = await conn.fetchrow(
#             """
#             INSERT INTO relances_client (client_id, vente_id, envoye_par, canal, message)
#             VALUES ($1, $2, $3, $4, $5)
#             RETURNING *
#             """,
#             client_id,
#             payload.vente_id,
#             current_user["id"],
#             payload.canal,
#             payload.message,
#         )
#     return RelanceOut(**dict(row))


# @router.get("/{client_id}/relances", response_model=list[RelanceOut])
# async def historique_relances(client_id: UUID, current_user: dict = Depends(get_current_user)):
#     pool = get_pool()
#     async with pool.acquire() as conn:
#         rows = await conn.fetch(
#             "SELECT * FROM relances_client WHERE client_id = $1 ORDER BY date_relance DESC", client_id
#         )
#     return [RelanceOut(**dict(r)) for r in rows]

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.database import get_pool
from app.schemas import (
    PaiementClientCreate,
    PaiementClientResult,
    PaiementHistoriqueOut,
    RelanceCreate,
    RelanceOut,
    TendanceDettes,
)

router = APIRouter(prefix="/dettes", tags=["Dettes"])


@router.get("")
async def lister_dettes(current_user: dict = Depends(get_current_user)):
    """Liste des clients ayant une dette, avec l'ancienneté de la dette
    (jours écoulés depuis la plus ancienne vente impayée) et le montant
    initialement dû, pour permettre le classement par urgence
    (Urgent > 30j, Moyen 15-30j, Récent < 15j) et l'affichage d'une jauge
    de remboursement côté application. Un VENDEUR ne voit que les dettes
    de ses propres clients/ventes."""
    condition_role = ""
    params: list = []
    if current_user["role"] == "VENDEUR":
        params.append(current_user["id"])
        condition_role = f" AND v.vendeur_id = ${len(params)}"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT c.id AS client_id, c.nom, c.prenom, c.telephone,
                   COALESCE(SUM(v.reste_a_payer) FILTER (WHERE v.reste_a_payer > 0), 0) AS solde_actuel,
                   COUNT(v.id) FILTER (WHERE v.reste_a_payer > 0) AS nombre_ventes_impayees,
                   MIN(v.date_echeance) FILTER (WHERE v.reste_a_payer > 0) AS prochaine_echeance,
                   (MIN(v.date_vente) FILTER (WHERE v.reste_a_payer > 0))::date AS date_plus_ancienne,
                   COALESCE(CURRENT_DATE - (MIN(v.date_vente) FILTER (WHERE v.reste_a_payer > 0))::date, 0) AS jours_ecoules,
                   COALESCE(SUM(v.montant_net) FILTER (WHERE v.reste_a_payer > 0), 0) AS montant_initial
            FROM clients c
            JOIN ventes v ON v.client_id = c.id
            WHERE TRUE {condition_role}
            GROUP BY c.id, c.nom, c.prenom, c.telephone
            HAVING COALESCE(SUM(v.reste_a_payer) FILTER (WHERE v.reste_a_payer > 0), 0) > 0
            ORDER BY solde_actuel DESC
            """,
            *params,
        )
    return [dict(r) for r in rows]


@router.get("/tendance", response_model=TendanceDettes)
async def tendance_dettes(current_user: dict = Depends(get_current_user)):
    """Résumé pour l'en-tête de l'écran des dettes : total actuel et
    comparaison du volume de nouvelles dettes générées ce mois-ci par
    rapport au mois précédent (indicateur de tendance ↑/↓)."""
    condition_role = ""
    params: list = []
    if current_user["role"] == "VENDEUR":
        params.append(current_user["id"])
        condition_role = f" AND vendeur_id = ${len(params)}"

    pool = get_pool()
    async with pool.acquire() as conn:
        if current_user["role"] == "VENDEUR":
            total_actuel = await conn.fetchval(
                "SELECT COALESCE(SUM(reste_a_payer), 0) FROM ventes WHERE reste_a_payer > 0 AND vendeur_id = $1",
                current_user["id"],
            )
            nb_clients = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT client_id) FROM ventes
                WHERE reste_a_payer > 0 AND client_id IS NOT NULL AND vendeur_id = $1
                """,
                current_user["id"],
            )
        else:
            total_actuel = await conn.fetchval(
                "SELECT COALESCE(SUM(reste_a_payer), 0) FROM ventes WHERE reste_a_payer > 0"
            )
            nb_clients = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT client_id) FROM ventes
                WHERE reste_a_payer > 0 AND client_id IS NOT NULL
                """
            )

        mois_courant = await conn.fetchval(
            f"""
            SELECT COALESCE(SUM(reste_a_payer), 0) FROM ventes
            WHERE reste_a_payer > 0
              AND date_trunc('month', date_vente) = date_trunc('month', CURRENT_DATE)
              {condition_role}
            """,
            *params,
        )
        mois_precedent = await conn.fetchval(
            f"""
            SELECT COALESCE(SUM(reste_a_payer), 0) FROM ventes
            WHERE reste_a_payer > 0
              AND date_trunc('month', date_vente) = date_trunc('month', CURRENT_DATE - INTERVAL '1 month')
              {condition_role}
            """,
            *params,
        )

    if mois_precedent > 0:
        variation = ((mois_courant - mois_precedent) / mois_precedent) * 100
    elif mois_courant > 0:
        variation = 100.0
    else:
        variation = 0.0

    return TendanceDettes(
        total_actuel=total_actuel,
        nouvelles_dettes_mois_courant=mois_courant,
        nouvelles_dettes_mois_precedent=mois_precedent,
        variation_pourcentage=round(variation, 1),
        nombre_clients_debiteurs=nb_clients,
    )


@router.get("/en-retard")
async def dettes_en_retard(current_user: dict = Depends(get_current_user)):
    """Ventes dont la date d'échéance est dépassée et qui ne sont pas soldées —
    utile pour la fonctionnalité 'Relancer les clients débiteurs'."""
    condition_role = ""
    params: list = []
    if current_user["role"] == "VENDEUR":
        params.append(current_user["id"])
        condition_role = f" AND v.vendeur_id = ${len(params)}"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT v.id, v.numero_facture, v.date_vente, v.date_echeance, v.reste_a_payer,
                   c.id AS client_id, c.nom, c.prenom, c.telephone
            FROM ventes v
            JOIN clients c ON c.id = v.client_id
            WHERE v.reste_a_payer > 0 AND v.date_echeance IS NOT NULL
              AND v.date_echeance < CURRENT_DATE {condition_role}
            ORDER BY v.date_echeance ASC
            """,
            *params,
        )
    return [dict(r) for r in rows]


@router.post("/{client_id}/payer", response_model=PaiementClientResult, status_code=201)
async def payer_dette_client(
    client_id: UUID, payload: PaiementClientCreate, current_user: dict = Depends(get_current_user)
):
    """Encaisse un paiement pour un client débiteur, réparti automatiquement
    sur ses ventes impayées en commençant par les plus anciennes (FIFO).
    C'est ce qui alimente l'écran d'encaissement : le vendeur saisit un
    montant global (jusqu'à 'Tout payer') sans avoir à choisir une facture
    précise. Un VENDEUR ne peut encaisser que sur ses propres ventes."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            condition_role = ""
            params: list = [client_id]
            if current_user["role"] == "VENDEUR":
                params.append(current_user["id"])
                condition_role = f"AND vendeur_id = ${len(params)}"

            ventes_ouvertes = await conn.fetch(
                f"""
                SELECT id, reste_a_payer FROM ventes
                WHERE client_id = $1 AND reste_a_payer > 0 {condition_role}
                ORDER BY date_vente ASC
                FOR UPDATE
                """,
                *params,
            )

            if not ventes_ouvertes:
                raise HTTPException(status_code=404, detail="Aucune dette trouvée pour ce client")

            total_du = sum(v["reste_a_payer"] for v in ventes_ouvertes)
            if payload.montant > total_du:
                raise HTTPException(
                    status_code=400,
                    detail=f"Le montant ({payload.montant}) dépasse la dette totale ({total_du})",
                )

            restant = payload.montant
            ventes_soldees = 0
            ventes_mises_a_jour = 0

            for vente in ventes_ouvertes:
                if restant <= 0:
                    break
                part = min(restant, vente["reste_a_payer"])
                nouveau_reste = vente["reste_a_payer"] - part
                nouveau_statut = "PAYE" if nouveau_reste == 0 else "PARTIEL"

                await conn.execute(
                    """
                    INSERT INTO paiements (vente_id, montant, mode_paiement, reference, encaisse_par)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    vente["id"],
                    part,
                    payload.mode_paiement,
                    payload.reference,
                    current_user["id"],
                )
                await conn.execute(
                    """
                    UPDATE ventes SET reste_a_payer = $2, avance = avance + $3, statut_paiement = $4,
                                       updated_at = now()
                    WHERE id = $1
                    """,
                    vente["id"],
                    nouveau_reste,
                    part,
                    nouveau_statut,
                )
                if nouveau_reste == 0:
                    ventes_soldees += 1
                ventes_mises_a_jour += 1
                restant -= part

            row = await conn.fetchrow(
                """
                UPDATE clients SET solde_actuel = solde_actuel - $2, updated_at = now()
                WHERE id = $1
                RETURNING solde_actuel
                """,
                client_id,
                payload.montant,
            )

    return PaiementClientResult(
        montant_paye=payload.montant,
        nouveau_solde=row["solde_actuel"],
        ventes_soldees=ventes_soldees,
        ventes_mises_a_jour=ventes_mises_a_jour,
    )


@router.get("/{client_id}/paiements", response_model=list[PaiementHistoriqueOut])
async def historique_paiements_client(client_id: UUID, current_user: dict = Depends(get_current_user)):
    """Historique chronologique de tous les paiements reçus d'un client,
    toutes ventes confondues — alimente la timeline de l'écran client."""
    condition_role = ""
    params: list = [client_id]
    if current_user["role"] == "VENDEUR":
        params.append(current_user["id"])
        condition_role = f"AND v.vendeur_id = ${len(params)}"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT p.id, p.vente_id, v.numero_facture, p.montant, p.mode_paiement,
                   p.date_paiement, p.reference
            FROM paiements p
            JOIN ventes v ON v.id = p.vente_id
            WHERE v.client_id = $1 {condition_role}
            ORDER BY p.date_paiement DESC
            """,
            *params,
        )
    return [PaiementHistoriqueOut(**dict(r)) for r in rows]


@router.post("/{client_id}/relancer", response_model=RelanceOut, status_code=201)
async def relancer_client(
    client_id: UUID, payload: RelanceCreate, current_user: dict = Depends(get_current_user)
):
    """Enregistre une relance envoyée à un client débiteur (section
    'Relancer les clients débiteurs'). Le canal EMAIL/SMS est journalisé
    ici ; l'envoi effectif nécessite de brancher un fournisseur d'email/SMS
    (ex: SendGrid, Twilio) dans un prochain incrément."""
    pool = get_pool()
    async with pool.acquire() as conn:
        client = await conn.fetchrow("SELECT id, solde_actuel FROM clients WHERE id = $1", client_id)
        if client is None:
            raise HTTPException(status_code=404, detail="Client introuvable")
        if client["solde_actuel"] <= 0:
            raise HTTPException(status_code=400, detail="Ce client n'a pas de dette en cours")

        row = await conn.fetchrow(
            """
            INSERT INTO relances_client (client_id, vente_id, envoye_par, canal, message)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            client_id,
            payload.vente_id,
            current_user["id"],
            payload.canal,
            payload.message,
        )
    return RelanceOut(**dict(row))


@router.get("/{client_id}/relances", response_model=list[RelanceOut])
async def historique_relances(client_id: UUID, current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM relances_client WHERE client_id = $1 ORDER BY date_relance DESC", client_id
        )
    return [RelanceOut(**dict(r)) for r in rows]