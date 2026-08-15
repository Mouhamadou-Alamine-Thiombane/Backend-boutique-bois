"""
Point d'entrée de l'API - Gestion de boutique de vente de bois en gros.
Lancer en local avec : uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import connect_db, disconnect_db
from app.routers import (
    achats,
    auth,
    bois,
    clients,
    depenses,
    dettes,
    export,
    notifications,
    paiements,
    parametres,
    stats,
    stock,
    tarifs,
    type_epaisseur,
    utilisateurs,
    ventes,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await disconnect_db()


app = FastAPI(
    title="API Gestion Boutique de Bois",
    description="API pour la gestion d'une boutique de vente de bois en gros : "
    "stocks, clients, ventes, dettes et statistiques.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(utilisateurs.router)
app.include_router(bois.router)
app.include_router(type_epaisseur.router)
app.include_router(tarifs.router)
app.include_router(clients.router)
app.include_router(ventes.router)
app.include_router(paiements.router)
app.include_router(dettes.router)
app.include_router(stock.router)
app.include_router(achats.router)
app.include_router(depenses.router)
app.include_router(stats.router)
app.include_router(notifications.router)
app.include_router(parametres.router)
app.include_router(export.router)


# @app.get("/", tags=["Santé"])
# async def health_check():
#     return {"status": "ok", "message": "API Boutique Bois opérationnelle"}

@app.api_route("/", methods=["GET", "HEAD"], tags=["Santé"])
async def health_check():
    return {"status": "ok", "message": "API Boutique Bois opérationnelle"}