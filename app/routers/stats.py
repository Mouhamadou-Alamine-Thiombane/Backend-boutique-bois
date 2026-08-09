from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth import get_current_user, require_super_admin
from app.database import get_pool
from app.schemas import DashboardStats, TopClient, TopProduit

router = APIRouter(prefix="/stats", tags=["Statistiques"])


@router.get("/dashboard", response_model=DashboardStats)
async def tableau_de_bord(current_user: dict = Depends(get_current_user)):
    """Indicateurs clés pour le tableau de bord (section 9 du cahier des
    charges). Le SUPER_ADMIN voit les chiffres globaux de la boutique ; un
    VENDEUR voit uniquement ses propres ventes et les dettes de ses
    clients, comme demandé pour l'accès limité du vendeur."""
    est_admin = current_user["role"] == "SUPER_ADMIN"
    pool = get_pool()
    async with pool.acquire() as conn:
        if est_admin:
            ventes_jour = await conn.fetchval(
                "SELECT COALESCE(SUM(montant_net), 0) FROM ventes WHERE date_vente::date = CURRENT_DATE"
            )
            ventes_mois = await conn.fetchval(
                """
                SELECT COALESCE(SUM(montant_net), 0) FROM ventes
                WHERE date_trunc('month', date_vente) = date_trunc('month', CURRENT_DATE)
                """
            )
            # Calculé à partir de ventes.reste_a_payer (et non
            # clients.solde_actuel) pour rester rigoureusement cohérent avec
            # le total affiché sur l'écran Dettes, qui utilise la même
            # source — évite tout écart entre les deux écrans.
            dettes_totales = await conn.fetchval(
                "SELECT COALESCE(SUM(reste_a_payer), 0) FROM ventes WHERE reste_a_payer > 0"
            )
            nb_clients = await conn.fetchval("SELECT COUNT(*) FROM clients")
        else:
            vid = current_user["id"]
            ventes_jour = await conn.fetchval(
                """
                SELECT COALESCE(SUM(montant_net), 0) FROM ventes
                WHERE date_vente::date = CURRENT_DATE AND vendeur_id = $1
                """,
                vid,
            )
            ventes_mois = await conn.fetchval(
                """
                SELECT COALESCE(SUM(montant_net), 0) FROM ventes
                WHERE date_trunc('month', date_vente) = date_trunc('month', CURRENT_DATE) AND vendeur_id = $1
                """,
                vid,
            )
            dettes_totales = await conn.fetchval(
                "SELECT COALESCE(SUM(reste_a_payer), 0) FROM ventes WHERE vendeur_id = $1", vid
            )
            nb_clients = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT client_id) FROM ventes
                WHERE vendeur_id = $1 AND client_id IS NOT NULL
                """,
                vid,
            )

        # Le stock et les alertes restent globaux (visibles par tous, en lecture seule)
        stock_total = float(await conn.fetchval("SELECT COALESCE(SUM(quantite), 0) FROM stock"))
        alertes = await conn.fetchval(
            """
            SELECT COUNT(*) FROM stock s JOIN bois b ON b.id = s.bois_id
            WHERE s.quantite <= b.seuil_alerte
            """
        )

    return DashboardStats(
        ventes_du_jour=ventes_jour,
        ventes_du_mois=ventes_mois,
        dettes_totales=dettes_totales,
        stock_total=stock_total,
        nombre_alertes_stock=alertes,
        nombre_clients=nb_clients,
    )


@router.get("/top-clients", response_model=list[TopClient])
async def top_clients(limite: int = 10, current_user: dict = Depends(get_current_user)):
    """Un VENDEUR ne voit le classement que parmi ses propres ventes."""
    condition_role = ""
    params: list = [limite]
    if current_user["role"] == "VENDEUR":
        params.append(current_user["id"])
        condition_role = f"AND v.vendeur_id = ${len(params)}"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT c.id AS client_id, (c.nom || ' ' || COALESCE(c.prenom, '')) AS nom_complet,
                   SUM(v.montant_net) AS total_achats, COUNT(v.id) AS nombre_ventes
            FROM clients c
            JOIN ventes v ON v.client_id = c.id
            WHERE TRUE {condition_role}
            GROUP BY c.id, c.nom, c.prenom
            ORDER BY total_achats DESC
            LIMIT $1
            """,
            *params,
        )
    return [TopClient(**dict(r)) for r in rows]


@router.get("/top-produits", response_model=list[TopProduit])
async def top_produits(
    date_debut: date | None = None,
    date_fin: date | None = None,
    limite: int = 10,
    current_user: dict = Depends(get_current_user),
):
    conditions = []
    params: list = [limite]
    if current_user["role"] == "VENDEUR":
        params.append(current_user["id"])
        conditions.append(f"v.vendeur_id = ${len(params)}")
    if date_debut is not None:
        params.append(date_debut)
        conditions.append(f"v.date_vente::date >= ${len(params)}")
    if date_fin is not None:
        params.append(date_fin)
        conditions.append(f"v.date_vente::date <= ${len(params)}")

    query = """
        SELECT b.id AS bois_id, b.nom AS bois_nom,
               SUM(lv.quantite) AS quantite_vendue, SUM(lv.sous_total) AS montant_total
        FROM ligne_vente lv
        JOIN bois b ON b.id = lv.bois_id
        JOIN ventes v ON v.id = lv.vente_id
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " GROUP BY b.id, b.nom ORDER BY quantite_vendue DESC LIMIT $1"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [TopProduit(**dict(r)) for r in rows]


@router.get("/ventes-par-periode")
async def ventes_par_periode(
    granularite: str = "jour",
    date_debut: date | None = None,
    date_fin: date | None = None,
    vendeur_id: UUID | None = None,
    current_user: dict = Depends(require_super_admin),
):
    """Rapports de ventes par jour/semaine/mois/année. Réservé au Super
    Admin. Si vendeur_id est fourni, ne retourne que les ventes de ce
    vendeur précis (alimente sa fiche individuelle dans Vendeurs & Équipe)."""
    trunc_map = {"jour": "day", "semaine": "week", "mois": "month", "annee": "year"}
    trunc = trunc_map.get(granularite, "day")

    conditions = []
    params: list = []
    if date_debut is not None:
        params.append(date_debut)
        conditions.append(f"date_vente::date >= ${len(params)}")
    if date_fin is not None:
        params.append(date_fin)
        conditions.append(f"date_vente::date <= ${len(params)}")
    if vendeur_id is not None:
        params.append(vendeur_id)
        conditions.append(f"vendeur_id = ${len(params)}")

    query = f"""
        SELECT date_trunc('{trunc}', date_vente) AS periode,
               COUNT(*) AS nombre_ventes, SUM(montant_net) AS chiffre_affaires
        FROM ventes
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " GROUP BY periode ORDER BY periode DESC LIMIT 60"

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


@router.get("/performance-vendeurs")
async def performance_vendeurs(current_user: dict = Depends(require_super_admin)):
    """Réservé au Super Admin : compare les performances de tous les
    vendeurs, une information qu'un vendeur ne doit pas voir sur ses
    collègues."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT u.id AS vendeur_id, (u.nom || ' ' || u.prenom) AS nom_complet,
                   COUNT(v.id) AS nombre_ventes, COALESCE(SUM(v.montant_net), 0) AS chiffre_affaires
            FROM utilisateurs u
            LEFT JOIN ventes v ON v.vendeur_id = u.id
            WHERE u.role = 'VENDEUR'
            GROUP BY u.id, u.nom, u.prenom
            ORDER BY chiffre_affaires DESC
            """
        )
    return [dict(r) for r in rows]
