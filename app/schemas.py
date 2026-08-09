"""
Schémas Pydantic (requêtes / réponses) pour toutes les entités de l'API.
"""
from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

RoleType = Literal["SUPER_ADMIN", "VENDEUR"]
TypeClient = Literal["PARTICULIER", "ENTREPRISE", "GROSSISTE"]
ModePaiement = Literal["ESPECES", "MOBILE_MONEY", "CHEQUE", "VIREMENT"]
StatutPaiement = Literal["PAYE", "PARTIEL", "IMPAYE"]
CategorieDepense = Literal[
    "TRANSPORT", "CHARGEMENT", "ELECTRICITE", "SALAIRE", "ENTRETIEN", "AUTRE"
]


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UtilisateurOut"


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------- Utilisateurs ----------
class UtilisateurCreate(BaseModel):
    nom: str
    prenom: str
    email: EmailStr
    password: str = Field(min_length=6)
    telephone: Optional[str] = None
    role: RoleType


class UtilisateurOut(BaseModel):
    id: UUID
    nom: str
    prenom: str
    email: EmailStr
    telephone: Optional[str] = None
    role: RoleType
    actif: bool

    class Config:
        from_attributes = True


# ---------- Bois ----------
class BoisCreate(BaseModel):
    nom: str
    categorie: Optional[str] = "Standard"
    unite: str = "pièce"
    seuil_alerte: int = 10
    image_url: Optional[str] = None


class BoisUpdate(BaseModel):
    nom: Optional[str] = None
    categorie: Optional[str] = None
    unite: Optional[str] = None
    seuil_alerte: Optional[int] = None
    image_url: Optional[str] = None
    actif: Optional[bool] = None


class BoisOut(BaseModel):
    id: UUID
    nom: str
    categorie: Optional[str]
    unite: str
    seuil_alerte: int
    image_url: Optional[str]
    actif: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Type Epaisseur ----------
class TypeEpaisseurCreate(BaseModel):
    designation: str
    epaisseur_mm: int
    ordre_affichage: int = 0


class TypeEpaisseurOut(BaseModel):
    id: UUID
    designation: str
    epaisseur_mm: int
    ordre_affichage: int

    class Config:
        from_attributes = True


# ---------- Tarif Bois ----------
TypeCalcul = Literal["DIMENSIONNEL", "UNITAIRE"]


class TarifBoisCreate(BaseModel):
    bois_id: UUID
    type_epaisseur_id: UUID
    prix_vente: int = Field(ge=0)
    prix_achat: int = Field(ge=0)
    type_calcul: TypeCalcul = "UNITAIRE"
    coefficient: float = Field(default=22, gt=0)
    longueur_fixe: Optional[float] = Field(default=None, gt=0)
    largeur_fixe: Optional[float] = Field(default=None, gt=0)


class TarifBoisUpdate(BaseModel):
    prix_vente: Optional[int] = Field(default=None, ge=0)
    prix_achat: Optional[int] = Field(default=None, ge=0)
    coefficient: Optional[float] = Field(default=None, gt=0)
    longueur_fixe: Optional[float] = Field(default=None, gt=0)
    largeur_fixe: Optional[float] = Field(default=None, gt=0)


class TarifBoisOut(BaseModel):
    id: UUID
    bois_id: UUID
    bois_nom: Optional[str] = None
    type_epaisseur_id: UUID
    type_designation: Optional[str] = None
    epaisseur_mm: Optional[int] = None
    prix_vente: int
    prix_achat: int
    type_calcul: TypeCalcul
    coefficient: float
    longueur_fixe: Optional[float] = None
    largeur_fixe: Optional[float] = None
    date_debut: date
    date_fin: Optional[date]
    actif: bool

    class Config:
        from_attributes = True


# ---------- Clients ----------
class ClientCreate(BaseModel):
    nom: str
    prenom: Optional[str] = None
    telephone: str
    adresse: Optional[str] = None
    email: Optional[EmailStr] = None
    type_client: TypeClient = "PARTICULIER"
    code_contribuable: Optional[str] = None
    plafond_credit: int = 0


class ClientUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    adresse: Optional[str] = None
    email: Optional[EmailStr] = None
    type_client: Optional[TypeClient] = None
    code_contribuable: Optional[str] = None
    plafond_credit: Optional[int] = None


class ClientOut(BaseModel):
    id: UUID
    nom: str
    prenom: Optional[str]
    telephone: str
    adresse: Optional[str]
    email: Optional[str]
    type_client: TypeClient
    plafond_credit: int
    solde_actuel: int
    actif: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Ventes ----------
class LigneVenteIn(BaseModel):
    bois_id: UUID
    type_epaisseur_id: UUID
    quantite: int = Field(gt=0)
    longueur: Optional[float] = Field(default=None, gt=0)
    largeur: Optional[float] = Field(default=None, gt=0)
    # Permet au vendeur de négocier un prix différent du calcul
    # automatique pour ce client (le prix "fixe" varie parfois selon le
    # client en pratique). Si absent, le prix calculé est utilisé tel quel.
    prix_override: Optional[int] = Field(default=None, ge=0)


class VenteCreate(BaseModel):
    client_id: Optional[UUID] = None
    lignes: list[LigneVenteIn]
    remise: int = Field(default=0, ge=0, le=100)
    mode_paiement: ModePaiement
    avance: int = Field(default=0, ge=0)
    date_echeance: Optional[date] = None
    commentaire: Optional[str] = None


class LigneVenteOut(BaseModel):
    id: UUID
    bois_id: UUID
    bois_nom: Optional[str] = None
    type_epaisseur_id: UUID
    type_designation: Optional[str] = None
    quantite: int
    prix_unitaire_vente: int
    sous_total: int
    longueur: Optional[float] = None
    largeur: Optional[float] = None

    class Config:
        from_attributes = True


class VenteOut(BaseModel):
    id: UUID
    numero_facture: str
    client_id: Optional[UUID]
    vendeur_id: Optional[UUID]
    date_vente: datetime
    montant_total: int
    remise: int
    montant_net: int
    statut_paiement: StatutPaiement
    mode_paiement: ModePaiement
    avance: int
    reste_a_payer: int
    date_echeance: Optional[date]
    commentaire: Optional[str]
    lignes: list[LigneVenteOut] = []

    class Config:
        from_attributes = True


# ---------- Paiements ----------
class PaiementCreate(BaseModel):
    vente_id: UUID
    montant: int = Field(gt=0)
    mode_paiement: ModePaiement
    reference: Optional[str] = None


class PaiementOut(BaseModel):
    id: UUID
    vente_id: UUID
    montant: int
    mode_paiement: ModePaiement
    date_paiement: datetime
    reference: Optional[str]

    class Config:
        from_attributes = True


# ---------- Stock ----------
class StockOut(BaseModel):
    bois_id: UUID
    bois_nom: str
    unite: str
    type_epaisseur_id: UUID
    type_designation: str
    quantite: float
    seuil_alerte: int
    en_alerte: bool
    updated_at: datetime

class ValorisationLigne(BaseModel):
    bois_id: UUID
    bois_nom: str
    unite: str
    quantite_totale: float
    valeur_totale: int

class StockValorisationOut(BaseModel):
    valeur_totale: int
    lignes: list[ValorisationLigne]

class AjustementStockCreate(BaseModel):
    bois_id: UUID
    type_epaisseur_id: UUID
    # Positif pour ajouter du stock, négatif pour en retirer.
    # Peut être décimal pour un bois suivi en m³ (ex: 2.5).
    quantite: float
    commentaire: Optional[str] = None


class MouvementStockOut(BaseModel):
    id: UUID
    bois_id: UUID
    type_epaisseur_id: UUID
    type: Literal["ENTREE", "SORTIE"]
    quantite: int
    prix_unitaire: Optional[int]
    commentaire: Optional[str]
    date_mouvement: datetime

    class Config:
        from_attributes = True


# ---------- Fournisseurs & Achats ----------
class FournisseurCreate(BaseModel):
    nom: str
    contact: Optional[str] = None
    telephone: Optional[str] = None
    adresse: Optional[str] = None
    email: Optional[EmailStr] = None


class FournisseurOut(BaseModel):
    id: UUID
    nom: str
    contact: Optional[str]
    telephone: Optional[str]
    adresse: Optional[str]
    email: Optional[str]

    class Config:
        from_attributes = True


class LigneAchatIn(BaseModel):
    bois_id: UUID
    type_epaisseur_id: UUID
    quantite: float = Field(gt=0)
    prix_unitaire_achat: int = Field(ge=0)


class AchatCreate(BaseModel):
    fournisseur_id: Optional[UUID] = None
    lignes: list[LigneAchatIn]
    commentaire: Optional[str] = None


class AchatOut(BaseModel):
    id: UUID
    fournisseur_id: Optional[UUID]
    date_achat: datetime
    montant_total: int
    statut: StatutPaiement
    commentaire: Optional[str]

    class Config:
        from_attributes = True


# ---------- Dépenses ----------
class DepenseCreate(BaseModel):
    libelle: str
    categorie: CategorieDepense
    montant: int = Field(ge=0)
    date_depense: date
    commentaire: Optional[str] = None


class DepenseOut(BaseModel):
    id: UUID
    libelle: str
    categorie: CategorieDepense
    montant: int
    date_depense: date
    commentaire: Optional[str]

    class Config:
        from_attributes = True


# ---------- Relances clients ----------
class RelanceCreate(BaseModel):
    canal: Literal["NOTIFICATION", "EMAIL", "SMS"] = "NOTIFICATION"
    vente_id: Optional[UUID] = None
    message: Optional[str] = None


class RelanceOut(BaseModel):
    id: UUID
    client_id: UUID
    vente_id: Optional[UUID]
    canal: str
    message: Optional[str]
    date_relance: datetime

    class Config:
        from_attributes = True


# ---------- Paramètres application ----------
class ParametreUpdate(BaseModel):
    valeur: str


class ParametreOut(BaseModel):
    cle: str
    valeur: str
    description: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------- Paiement consolidé d'un client (écran d'encaissement) ----------
class PaiementClientCreate(BaseModel):
    montant: int = Field(gt=0)
    mode_paiement: ModePaiement
    reference: Optional[str] = None


class PaiementClientResult(BaseModel):
    montant_paye: int
    nouveau_solde: int
    ventes_soldees: int
    ventes_mises_a_jour: int


class PaiementHistoriqueOut(BaseModel):
    id: UUID
    vente_id: UUID
    numero_facture: str
    montant: int
    mode_paiement: str
    date_paiement: datetime
    reference: Optional[str] = None


class TendanceDettes(BaseModel):
    total_actuel: int
    nouvelles_dettes_mois_courant: int
    nouvelles_dettes_mois_precedent: int
    variation_pourcentage: float
    nombre_clients_debiteurs: int


# ---------- Notifications ----------
class NotificationOut(BaseModel):
    id: UUID
    type: str
    message: str
    est_lu: bool
    date_creation: datetime

    class Config:
        from_attributes = True


# ---------- Statistiques ----------
class DashboardStats(BaseModel):
    ventes_du_jour: int
    ventes_du_mois: int
    dettes_totales: int
    stock_total: float
    nombre_alertes_stock: int
    nombre_clients: int


class TopClient(BaseModel):
    client_id: UUID
    nom_complet: str
    total_achats: int
    nombre_ventes: int


class TopProduit(BaseModel):
    bois_id: UUID
    bois_nom: str
    quantite_vendue: int
    montant_total: int
