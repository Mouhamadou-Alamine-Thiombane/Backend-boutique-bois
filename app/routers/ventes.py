from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_any_role
from app.database import get_pool
from app.schemas import VenteCreate, VenteOut, LigneVenteOut

router = APIRouter(prefix="/ventes", tags=["Ventes"])


async def _generer_numero_facture(conn) -> str:
    today = datetime.now().strftime("%Y%m%d")
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM ventes WHERE numero_facture LIKE $1", f"FACT-{today}-%"
    )
    return f"FACT-{today}-{count + 1:05d}"


@router.post("", response_model=VenteOut, status_code=201)
async def enregistrer_vente(payload: VenteCreate, current_user: dict = Depends(require_any_role)):
    """Enregistre une vente complète.

    Le prix de chaque ligne est calculé automatiquement :
        DIMENSIONNEL : prix_piece = (prix_vente / coefficient) × longueur × largeur
        UNITAIRE      : prix_piece = prix_vente (fixe)
    Le vendeur peut ensuite AJUSTER ce prix pour un client donné (remise
    négociée, prix VIP, etc.) via `ligne.prix_override` — si fourni, ce
    prix remplace le calcul automatique pour cette ligne uniquement.

    Le suivi de stock a été retiré : aucune vérification de disponibilité
    n'est effectuée, la vente est toujours acceptée quelle que soit la
    quantité demandée.
    """
    if not payload.lignes:
        raise HTTPException(status_code=400, detail="La vente doit contenir au moins une ligne")

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            lignes_calculees = []
            montant_total = 0

            for ligne in payload.lignes:
                tarif = await conn.fetchrow(
                    """
                    SELECT prix_vente, type_calcul, coefficient, longueur_fixe, largeur_fixe
                    FROM tarif_bois
                    WHERE bois_id = $1 AND type_epaisseur_id = $2
                      AND actif = TRUE AND date_fin IS NULL
                    """,
                    ligne.bois_id,
                    ligne.type_epaisseur_id,
                )
                if tarif is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Aucun tarif actif pour ce bois/épaisseur ({ligne.bois_id})",
                    )

                if tarif["type_calcul"] == "DIMENSIONNEL":
                    longueur = ligne.longueur
                    largeur = ligne.largeur
                    if not longueur or not largeur:
                        raise HTTPException(
                            status_code=400,
                            detail="La longueur et la largeur sont requises pour ce bois (tarification dimensionnelle)",
                        )
                    coefficient = float(tarif["coefficient"])
                    prix_calcule = round(tarif["prix_vente"] / coefficient * longueur * largeur)
                else:
                    longueur_fixe = tarif["longueur_fixe"]
                    largeur_fixe = tarif["largeur_fixe"]
                    longueur = ligne.longueur or (float(longueur_fixe) if longueur_fixe is not None else None)
                    largeur = ligne.largeur or (float(largeur_fixe) if largeur_fixe is not None else None)
                    prix_calcule = tarif["prix_vente"]

                # Le vendeur peut négocier un prix différent du calcul
                # automatique pour ce client précis.
                prix_unitaire = ligne.prix_override if ligne.prix_override is not None else prix_calcule

                sous_total = prix_unitaire * ligne.quantite
                montant_total += sous_total
                lignes_calculees.append(
                    {
                        "bois_id": ligne.bois_id,
                        "type_epaisseur_id": ligne.type_epaisseur_id,
                        "quantite": ligne.quantite,
                        "prix_unitaire_vente": prix_unitaire,
                        "sous_total": sous_total,
                        "longueur": longueur,
                        "largeur": largeur,
                    }
                )

            montant_net = montant_total - (montant_total * payload.remise // 100)

            if payload.avance > montant_net:
                raise HTTPException(status_code=400, detail="L'avance ne peut pas dépasser le montant net")

            reste_a_payer = montant_net - payload.avance
            if reste_a_payer == 0:
                statut_paiement = "PAYE"
            elif payload.avance > 0:
                statut_paiement = "PARTIEL"
            else:
                statut_paiement = "IMPAYE"

            if payload.client_id is not None and reste_a_payer > 0:
                client = await conn.fetchrow(
                    "SELECT plafond_credit, solde_actuel FROM clients WHERE id = $1",
                    payload.client_id,
                )
                if client is None:
                    raise HTTPException(status_code=404, detail="Client introuvable")
                if client["plafond_credit"] > 0 and (
                    client["solde_actuel"] + reste_a_payer > client["plafond_credit"]
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Cette vente dépasserait le plafond de crédit du client",
                    )

            numero_facture = await _generer_numero_facture(conn)

            vente_id = await conn.fetchval(
                """
                INSERT INTO ventes (numero_facture, client_id, vendeur_id, montant_total, remise,
                                     montant_net, statut_paiement, mode_paiement, avance,
                                     reste_a_payer, date_echeance, commentaire)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING id
                """,
                numero_facture,
                payload.client_id,
                current_user["id"],
                montant_total,
                payload.remise,
                montant_net,
                statut_paiement,
                payload.mode_paiement,
                payload.avance,
                reste_a_payer,
                payload.date_echeance,
                payload.commentaire,
            )

            for lc in lignes_calculees:
                await conn.execute(
                    """
                    INSERT INTO ligne_vente (vente_id, bois_id, type_epaisseur_id, quantite,
                                              prix_unitaire_vente, sous_total, longueur, largeur)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    vente_id,
                    lc["bois_id"],
                    lc["type_epaisseur_id"],
                    lc["quantite"],
                    lc["prix_unitaire_vente"],
                    lc["sous_total"],
                    lc["longueur"],
                    lc["largeur"],
                )

            if payload.avance > 0 and payload.client_id is not None:
                await conn.execute(
                    """
                    INSERT INTO paiements (vente_id, montant, mode_paiement, encaisse_par)
                    VALUES ($1, $2, $3, $4)
                    """,
                    vente_id,
                    payload.avance,
                    payload.mode_paiement,
                    current_user["id"],
                )

            if payload.client_id is not None:
                await conn.execute(
                    "UPDATE clients SET solde_actuel = solde_actuel + $2, updated_at = now() WHERE id = $1",
                    payload.client_id,
                    reste_a_payer,
                )

    return await _get_vente_complete(vente_id)


async def _get_vente_complete(vente_id: UUID) -> VenteOut:
    pool = get_pool()
    async with pool.acquire() as conn:
        vente_row = await conn.fetchrow("SELECT * FROM ventes WHERE id = $1", vente_id)
        lignes_rows = await conn.fetch(
            """
            SELECT lv.*, b.nom AS bois_nom, te.designation AS type_designation
            FROM ligne_vente lv
            JOIN bois b ON b.id = lv.bois_id
            JOIN type_epaisseur te ON te.id = lv.type_epaisseur_id
            WHERE lv.vente_id = $1
            """,
            vente_id,
        )
    data = dict(vente_row)
    data["lignes"] = [LigneVenteOut(**dict(r)) for r in lignes_rows]
    return VenteOut(**data)


@router.get("", response_model=list[VenteOut])
async def lister_ventes(
    client_id: UUID | None = None,
    vendeur_id: UUID | None = None,
    statut_paiement: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Liste des ventes. Un VENDEUR ne voit que ses propres ventes (le
    paramètre vendeur_id est ignoré pour lui, sa restriction prime
    toujours). Le SUPER_ADMIN peut filtrer par vendeur précis via
    vendeur_id, utile pour consulter la fiche d'un membre de l'équipe."""
    conditions = []
    params: list = []
    if current_user["role"] == "VENDEUR":
        params.append(current_user["id"])
        conditions.append(f"vendeur_id = ${len(params)}")
    elif vendeur_id is not None:
        params.append(vendeur_id)
        conditions.append(f"vendeur_id = ${len(params)}")
    if client_id is not None:
        params.append(client_id)
        conditions.append(f"client_id = ${len(params)}")
    if statut_paiement is not None:
        params.append(statut_paiement)
        conditions.append(f"statut_paiement = ${len(params)}")

    query = "SELECT id FROM ventes"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY date_vente DESC LIMIT 200"

    pool = get_pool()
    async with pool.acquire() as conn:
        ids = [r["id"] for r in await conn.fetch(query, *params)]

    return [await _get_vente_complete(vid) for vid in ids]

@router.get("/{vente_id}", response_model=VenteOut)
async def obtenir_vente(vente_id: UUID, current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, vendeur_id FROM ventes WHERE id = $1", vente_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vente introuvable")
    if current_user["role"] == "VENDEUR" and str(row["vendeur_id"]) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Vous ne pouvez consulter que vos propres ventes")
    return await _get_vente_complete(vente_id)