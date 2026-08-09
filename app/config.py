"""
Configuration de l'application - lecture des variables d'environnement.
Copiez .env.example vers .env et remplissez avec vos identifiants Supabase/PostgreSQL.
"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field


class Settings(BaseSettings):
    # Connexion PostgreSQL (Supabase fournit cette chaine dans
    # Project Settings > Database > Connection string)
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/boutique_bois"

    # Sécurité JWT
    jwt_secret: str = "changez-moi-en-production-avec-une-cle-longue-et-aleatoire"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  # 12h
    refresh_token_expire_days: int = 30

    # CORS - domaines autorisés à appeler l'API (app Flutter web, mobile, etc.)
    cors_origins: list[str] = ["*"]

    # Configuration Pydantic v2 (remplace class Config)
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ✅ Ignore les variables non déclarées
        case_sensitive=True  # Conserve la casse (DATABASE_URL)
    )


settings = Settings()