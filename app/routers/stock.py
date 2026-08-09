from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_super_admin
from app.database import get_pool
from app.schemas import AjustementStockCreate, MouvementStockOut, StockOut, StockValorisationOut

router = APIRouter(prefix="/stock", tags=["Stock"])

SELECT_STOCK_LIGNE = """
    SELECT s.bois_id, b.nom AS bois_nom, b.unite, s.type_epaisseur_id,
           te.designation AS type_designation,
           s.quantite, b.seuil_alerte, (s.quantite <= b.seuil_alerte) AS en_alerte, s.updated_at
    FROM stock s
    JOIN bois b ON b.id = s.bois_id
    JOIN type_epaisseur te ON te.id = s.type_epaisseur_id
    WHERE s.bois_id = $1 AND s.type_epaisseur_id = $2
"""


@router.get("", response_model=list[StockOut])
async def lister_stock(en_alerte_seulement: bool = False, current_user: dict = Depends(get_current_user)):
    """Liste du stock disponible par bois + épaisseur. Pour un bois suivi
    en m³ (Rouge, Fracké, Dubetou), `quantite` représente un volume en m³ ;
    pour les autres (Samba, Sapin), un nombre de pièces — voir `unite`."""
    pool = get_pool()
    query = """
        SELECT s.bois_id, b.nom AS bois_nom, b.unite, s.type_epaisseur_id,
               te.designation AS type_designation,
               s.quantite, b.seuil_alerte, (s.quantite <= b.seuil_alerte) AS en_alerte, s.updated_at
        FROM stock s
        JOIN bois b ON b.id = s.bois_id
        JOIN type_epaisseur te ON te.id = s.type_epaisseur_id
    """
    if en_alerte_seulement:
        query += " WHERE s.quantite <= b.seuil_alerte"
    query += " ORDER BY b.nom, te.ordre_affichage"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
    return [StockOut(**dict(r)) for r in rows]


@router.get("/valorisation", response_model=StockValorisationOut)
async def valoriser_stock(current_user: dict = Depends(require_super_admin)):
    """Valeur totale du stock (bilan/inventaire), calculée au coût
    d'achat : pour un bois en m³, quantite(m³) × prix_achat_actif(par m³) ;
    pour un bois en pièces, quantite(pièces) × prix_achat_actif(par pièce).
    N'affecte jamais le prix de vente au client — c'est un indicateur de
    valeur d'inventaire uniquement."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT b.id AS bois_id, b.nom AS bois_nom, b.unite,
                   SUM(s.quantite) AS quantite_totale,
                   COALESCE(SUM(s.quantite * t.prix_achat), 0) AS valeur_totale
            FROM stock s
            JOIN bois b ON b.id = s.bois_id
            LEFT JOIN tarif_bois t
                ON t.bois_id = s.bois_id AND t.type_epaisseur_id = s.type_epaisseur_id
                AND t.actif = TRUE AND t.date_fin IS NULL
            GROUP BY b.id, b.nom, b.unite
            HAVING SUM(s.quantite) > 0
            ORDER BY valeur_totale DESC
            """
        )
    lignes = [dict(r) for r in rows]
    valeur_totale = round(sum(float(l["valeur_totale"]) for l in lignes))
    return StockValorisationOut(
        valeur_totale=valeur_totale,
        lignes=[
            {
                "bois_id": l["bois_id"],
                "bois_nom": l["bois_nom"],
                "unite": l["unite"],
                "quantite_totale": float(l["quantite_totale"]),
                "valeur_totale": round(float(l["valeur_totale"])),
            }
            for l in lignes
        ],
    )


@router.post("/ajuster", response_model=StockOut, status_code=201)
async def ajuster_stock(payload: AjustementStockCreate, current_user: dict = Depends(require_super_admin)):
    """Ajoute ou retire manuellement du stock pour un bois/épaisseur, sans
    passer par un achat fournisseur — utile pour un inventaire initial ou
    une correction (casse, erreur de comptage...). Quantité positive =
    ajout, négative = retrait. Peut être décimale pour un bois suivi en m³
    (ex: -0.5 pour retirer un demi mètre cube). Réservé au Super Admin."""
    pool = get_pool()
    async with pool.acquire() as conn:
        bois = await conn.fetchval("SELECT id FROM bois WHERE id = $1", payload.bois_id)
        if bois is None:
            raise HTTPException(status_code=404, detail="Bois introuvable")
        type_epaisseur = await conn.fetchval(
            "SELECT id FROM type_epaisseur WHERE id = $1", payload.type_epaisseur_id
        )
        if type_epaisseur is None:
            raise HTTPException(status_code=404, detail="Type d'épaisseur introuvable")

        async with conn.transaction():
            quantite_actuelle = (
                await conn.fetchval(
                    "SELECT quantite FROM stock WHERE bois_id = $1 AND type_epaisseur_id = $2",
                    payload.bois_id,
                    payload.type_epaisseur_id,
                )
                or 0
            )
            nouvelle_quantite = float(quantite_actuelle) + payload.quantite
            if nouvelle_quantite < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuffisant pour retirer {abs(payload.quantite)} "
                    f"(disponible: {quantite_actuelle})",
                )

            await conn.execute(
                """
                INSERT INTO stock (bois_id, type_epaisseur_id, quantite)
                VALUES ($1, $2, $3)
                ON CONFLICT (bois_id, type_epaisseur_id)
                DO UPDATE SET quantite = $3, updated_at = now()
                """,
                payload.bois_id,
                payload.type_epaisseur_id,
                nouvelle_quantite,
            )
            await conn.execute(
                """
                INSERT INTO mouvement_stock (bois_id, type_epaisseur_id, type, quantite, commentaire)
                VALUES ($1, $2, $3, $4, $5)
                """,
                payload.bois_id,
                payload.type_epaisseur_id,
                "ENTREE" if payload.quantite >= 0 else "SORTIE",
                abs(payload.quantite),
                payload.commentaire or "Ajustement manuel de stock",
            )

        row = await conn.fetchrow(SELECT_STOCK_LIGNE, payload.bois_id, payload.type_epaisseur_id)
    return StockOut(**dict(row))


@router.get("/mouvements", response_model=list[MouvementStockOut])
async def lister_mouvements(limit: int = 100, current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM mouvement_stock ORDER BY date_mouvement DESC LIMIT $1", limit
        )
    return [MouvementStockOut(**dict(r)) for r in rows]