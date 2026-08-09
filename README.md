# Backend — API Gestion Boutique de Bois

API FastAPI pour la gestion d'une boutique de vente de bois en gros
(stocks, clients, ventes, dettes, statistiques), connectée à une base
PostgreSQL hébergée sur Supabase.

## 1. Mise en place de la base de données

1. Créez un projet sur [supabase.com](https://supabase.com).
2. Ouvrez **SQL Editor** dans le tableau de bord Supabase.
3. Copiez-collez le contenu de `../database/schema.sql` et exécutez-le.
   Cela crée les 17 tables, les vues, les fonctions et les déclencheurs
   (triggers) qui automatisent la mise à jour des stocks et des soldes
   clients.
4. Copiez-collez ensuite le contenu de `../database/migration_v2.sql` et
   exécutez-le (ajoute le suivi des relances clients et les paramètres
   configurables de l'application).
5. (Optionnel) Exécutez `../database/seed.sql` pour insérer des données
   de démonstration (bois, épaisseurs, tarifs, un compte Super Admin).
6. Récupérez la chaîne de connexion : **Project Settings > Database >
   Connection string > URI**.

## 2. Installation du backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Éditez .env et collez votre DATABASE_URL Supabase + un JWT_SECRET aléatoire
```

## 3. Lancer le serveur en local

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

L'API est alors disponible sur `http://localhost:8000`, avec une
documentation interactive auto-générée sur `http://localhost:8000/docs`
(Swagger UI) et `http://localhost:8000/redoc`.

## 4. Créer le premier compte Super Admin

Si vous n'avez pas exécuté `seed.sql`, créez le premier administrateur
directement en base (car la création d'utilisateur via l'API nécessite déjà
d'être Super Admin) :

```sql
INSERT INTO utilisateurs (nom, prenom, email, password_hash, role)
VALUES ('Admin', 'Principal', 'admin@boutique.sn',
        '$2b$12$REMPLACEZ_PAR_UN_HASH_BCRYPT', 'SUPER_ADMIN');
```

Générez le hash bcrypt avec Python :
```bash
python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('votre_mot_de_passe'))"
```

Ensuite, connectez-vous via `POST /auth/login` pour obtenir un token JWT et
créer les autres utilisateurs (vendeurs) via `POST /utilisateurs`.

## 5. Structure du projet

```
app/
├── main.py              # Point d'entrée, montage des routers, CORS
├── config.py             # Lecture des variables d'environnement
├── database.py            # Pool de connexions PostgreSQL (asyncpg)
├── auth.py               # JWT, hachage des mots de passe, rôles
├── schemas.py             # Modèles Pydantic (requêtes/réponses)
└── routers/
    ├── auth.py             # Connexion, rafraîchissement de token
    ├── utilisateurs.py      # Gestion des comptes vendeurs (Super Admin)
    ├── bois.py              # Types de bois (flexible, création/suppression)
    ├── type_epaisseur.py      # Types d'épaisseur (1T, 2T, 3T... flexible)
    ├── tarifs.py             # Prix par bois/épaisseur, historisés
    ├── clients.py            # Clients, filtrés par vendeur si applicable
    ├── ventes.py             # Enregistrement des ventes (cœur métier)
    ├── paiements.py           # Paiements de dettes
    ├── dettes.py             # Suivi, ancienneté, tendance, encaissement consolidé, relances
    ├── stock.py              # Niveaux de stock et mouvements
    ├── achats.py             # Fournisseurs, achats (Super Admin)
    ├── depenses.py            # Dépenses (Super Admin)
    ├── stats.py              # Tableau de bord (global ou personnel selon le rôle)
    ├── parametres.py          # Paramètres configurables (Super Admin)
    ├── export.py              # Export CSV/Excel des rapports (Super Admin)
    └── notifications.py       # Notifications utilisateur
```

## 6. Gestion des dettes

Le module `dettes.py` expose :

- `GET /dettes` — liste des clients débiteurs, avec `jours_ecoules` (ancienneté de la plus vieille vente impayée) et `montant_initial` (pour calculer un pourcentage de remboursement côté application).
- `GET /dettes/tendance` — total actuel et comparaison du volume de nouvelles dettes entre ce mois-ci et le mois précédent (alimente la flèche de tendance de l'écran).
- `POST /dettes/{client_id}/payer` — encaisse un montant pour un client et le répartit automatiquement sur ses ventes impayées les plus anciennes (FIFO), sans que l'utilisateur ait à choisir une facture précise.
- `GET /dettes/{client_id}/paiements` — historique chronologique de tous les paiements du client, toutes ventes confondues.
- `POST /dettes/{client_id}/relancer` / `GET /dettes/{client_id}/relances` — envoi et historique des relances (canal Notification/Email/SMS).

## 7. Séparation des rôles

Chaque endpoint applique le contrôle d'accès au niveau de la dépendance
FastAPI (`require_super_admin` ou `get_current_user` avec filtrage), pas
seulement côté interface. Un Vendeur qui appelle directement l'API ne
peut donc jamais voir les ventes, clients ou dettes d'un autre vendeur,
ni accéder aux endpoints Fournisseurs, Achats, Dépenses, Export ou
Paramètres, réservés au Super Admin. Voir le tableau de répartition des
droits dans le `README.md` à la racine du projet.

## 8. Déploiement

Ce backend peut être déployé sur Railway, Render, Fly.io, ou toute
plateforme supportant Python/ASGI. Pensez à définir les variables
d'environnement (`DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`) sur la
plateforme choisie, et à restreindre `CORS_ORIGINS` à votre domaine réel
avant la mise en production (ne pas laisser `["*"]`).
