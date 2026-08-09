from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_super_admin
from app.database import get_pool
from app.schemas import TarifBoisCreate, TarifBoisOut, TarifBoisUpdate

router = APIRouter(prefix="/tarifs", tags=["Tarifs"])

SELECT_TARIF = """
    SELECT
        t.id, t.bois_id, b.nom AS bois_nom,
        t.type_epaisseur_id, te.designation AS type_designation, te.epaisseur_mm,
        t.prix_vente, t.prix_achat, t.type_calcul, t.coefficient,
        t.longueur_fixe, t.largeur_fixe, t.date_debut, t.date_fin, t.actif
    FROM tarif_bois t
    JOIN bois b ON b.id = t.bois_id
    JOIN type_epaisseur te ON te.id = t.type_epaisseur_id
"""


@router.get("", response_model=list[TarifBoisOut])
async def lister_tarifs(
    bois_id: UUID | None = None,
    actifs_seulement: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """Retourne les tarifs disponibles. Par défaut, seuls les tarifs actifs
    et en cours de validité (date_fin IS NULL) sont retournés, triés par
    ordre_affichage du type d'épaisseur — comme décrit en section 3.2.2."""
    conditions = []
    params: list = []
    if actifs_seulement:
        conditions.append("t.actif = TRUE AND t.date_fin IS NULL")
    if bois_id is not None:
        params.append(bois_id)
        conditions.append(f"t.bois_id = ${len(params)}")

    query = SELECT_TARIF
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY b.nom, te.ordre_affichage"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [TarifBoisOut(**dict(r)) for r in rows]


@router.post("", response_model=TarifBoisOut, status_code=201)
async def creer_tarif(payload: TarifBoisCreate, current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            """
            SELECT id FROM tarif_bois
            WHERE bois_id = $1 AND type_epaisseur_id = $2 AND actif = TRUE AND date_fin IS NULL
            """,
            payload.bois_id,
            payload.type_epaisseur_id,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Un tarif actif existe déjà pour ce bois/épaisseur. Utilisez la mise à jour de prix.",
            )

        tarif_id = await conn.fetchval(
            """
            INSERT INTO tarif_bois (bois_id, type_epaisseur_id, prix_vente, prix_achat,
                                     type_calcul, coefficient, longueur_fixe, largeur_fixe, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            payload.bois_id,
            payload.type_epaisseur_id,
            payload.prix_vente,
            payload.prix_achat,
            payload.type_calcul,
            payload.coefficient,
            payload.longueur_fixe,
            payload.largeur_fixe,
            current_user["id"],
        )
        row = await conn.fetchrow(SELECT_TARIF + " WHERE t.id = $1", tarif_id)
    return TarifBoisOut(**dict(row))


@router.put("/{tarif_id}", response_model=TarifBoisOut)
async def modifier_prix(
    tarif_id: UUID, payload: TarifBoisUpdate, current_user: dict = Depends(require_super_admin)
):
    """Modifier un prix clôture l'ancien tarif et en crée un nouveau
    (historique préservé). Si un tarif a déjà été créé aujourd'hui pour ce
    bois/épaisseur (ex: deuxième modification le même jour), on met à jour
    cette ligne du jour directement plutôt que d'en créer une deuxième —
    la base interdit deux tarifs pour la même date."""
    pool = get_pool()
    async with pool.acquire() as conn:
        old = await conn.fetchrow("SELECT * FROM tarif_bois WHERE id = $1", tarif_id)
        if old is None:
            raise HTTPException(status_code=404, detail="Tarif introuvable")

        new_prix_vente = payload.prix_vente if payload.prix_vente is not None else old["prix_vente"]
        new_prix_achat = payload.prix_achat if payload.prix_achat is not None else old["prix_achat"]
        new_coefficient = payload.coefficient if payload.coefficient is not None else old["coefficient"]
        new_longueur_fixe = payload.longueur_fixe if payload.longueur_fixe is not None else old["longueur_fixe"]
        new_largeur_fixe = payload.largeur_fixe if payload.largeur_fixe is not None else old["largeur_fixe"]

        async with conn.transaction():
            tarif_du_jour = await conn.fetchrow(
                """
                SELECT id FROM tarif_bois
                WHERE bois_id = $1 AND type_epaisseur_id = $2 AND date_debut = CURRENT_DATE
                """,
                old["bois_id"],
                old["type_epaisseur_id"],
            )

            if tarif_du_jour is not None:
                await conn.execute(
                    """
                    UPDATE tarif_bois
                    SET prix_vente = $2, prix_achat = $3, coefficient = $4,
                        longueur_fixe = $5, largeur_fixe = $6, actif = TRUE, date_fin = NULL
                    WHERE id = $1
                    """,
                    tarif_du_jour["id"],
                    new_prix_vente,
                    new_prix_achat,
                    new_coefficient,
                    new_longueur_fixe,
                    new_largeur_fixe,
                )
                new_id = tarif_du_jour["id"]
                if old["id"] != new_id:
                    await conn.execute(
                        "UPDATE tarif_bois SET date_fin = CURRENT_DATE, actif = FALSE WHERE id = $1 AND date_fin IS NULL",
                        old["id"],
                    )
            else:
                await conn.execute(
                    "UPDATE tarif_bois SET date_fin = CURRENT_DATE, actif = FALSE WHERE id = $1",
                    tarif_id,
                )
                new_id = await conn.fetchval(
                    """
                    INSERT INTO tarif_bois (bois_id, type_epaisseur_id, prix_vente, prix_achat,
                                             type_calcul, coefficient, longueur_fixe, largeur_fixe, created_by)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id
                    """,
                    old["bois_id"],
                    old["type_epaisseur_id"],
                    new_prix_vente,
                    new_prix_achat,
                    old["type_calcul"],
                    new_coefficient,
                    new_longueur_fixe,
                    new_largeur_fixe,
                    current_user["id"],
                )
        row = await conn.fetchrow(SELECT_TARIF + " WHERE t.id = $1", new_id)
    return TarifBoisOut(**dict(row))


@router.patch("/{tarif_id}/desactiver", status_code=204)
async def desactiver_tarif(tarif_id: UUID, current_user: dict = Depends(require_super_admin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE tarif_bois SET actif = FALSE, date_fin = CURRENT_DATE WHERE id = $1", tarif_id
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Tarif introuvable")


@router.delete("/{tarif_id}", status_code=204)
async def supprimer_tarif(tarif_id: UUID, current_user: dict = Depends(require_super_admin)):
    """Supprime définitivement un tarif jamais utilisé dans une vente.
    Si ce tarif a déjà servi à une vente, il est refusé de le supprimer
    (l'historique des prix doit rester consultable) — utilisez la
    désactivation à la place."""
    pool = get_pool()
    async with pool.acquire() as conn:
        tarif = await conn.fetchrow(
            "SELECT bois_id, type_epaisseur_id, date_debut, date_fin FROM tarif_bois WHERE id = $1",
            tarif_id,
        )
        if tarif is None:
            raise HTTPException(status_code=404, detail="Tarif introuvable")

        # Une vente est considérée comme ayant utilisé ce tarif si elle
        # porte sur le même bois/épaisseur et a eu lieu pendant la période
        # de validité de ce tarif (peu importe le mode de calcul du prix).
        deja_utilise = await conn.fetchval(
            """
            SELECT 1 FROM ligne_vente lv
            JOIN ventes v ON v.id = lv.vente_id
            WHERE lv.bois_id = $1 AND lv.type_epaisseur_id = $2
              AND v.date_vente::date >= $3
              AND ($4::date IS NULL OR v.date_vente::date <= $4)
            LIMIT 1
            """,
            tarif["bois_id"],
            tarif["type_epaisseur_id"],
            tarif["date_debut"],
            tarif["date_fin"],
        )
        if deja_utilise:
            raise HTTPException(
                status_code=409,
                detail="Ce tarif a déjà été utilisé dans une vente. Désactivez-le plutôt que de le supprimer.",
            )
        result = await conn.execute("DELETE FROM tarif_bois WHERE id = $1", tarif_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Tarif introuvable")


@router.get("/historique/{bois_id}/{type_epaisseur_id}", response_model=list[TarifBoisOut])
async def historique_prix(
    bois_id: UUID, type_epaisseur_id: UUID, current_user: dict = Depends(get_current_user)
):
    """Historique complet des prix pour une combinaison bois + épaisseur (section 4.5)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            SELECT_TARIF
            + " WHERE t.bois_id = $1 AND t.type_epaisseur_id = $2 ORDER BY t.date_debut DESC",
            bois_id,
            type_epaisseur_id,
        )
    return [TarifBoisOut(**dict(r)) for r in rows]
