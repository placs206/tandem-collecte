"""Règles de constat (v0.1) : des faits extraits aux résultats d'obligations, par séance.

Déterministe, sans IA (spécification section 4). Produit des objets `engine.Seance` prêts pour `engine.calculer`.
Règles : P47 (absent = non), P53 (conditionnel), P55/P56 (gérés par le moteur), P57 (douteux = à vérifier),
P60 (toutes les délibérations numérotées retrouvées), DN-07, DN-13 (extrait du registre ≠ PV), DN-27 à DN-30.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Set

from engine import AV, NA, NON, OUI, Seance, charger_catalogue

VERSION_REGLES = "constats-0.1"

# Type de pièce (typage.py) -> document attesté pour le moteur (DN-13 : l'extrait atteste les délibérations, pas le PV)
TYPE_VERS_DOC = {"PV": "PV", "EXTRAIT_REGISTRE": "DELIB", "DELIB": "DELIB", "LISTE_DELIB": "LISTE"}

# Obligation « par PV » -> faits qui doivent tous être présents dans le PV
FAITS_PV = {
    "PV-01": ["seance_date", "heure"],
    "PV-02": ["president"],
    "PV-03": ["presents"],
    "PV-04": ["secretaire"],
    "PV-05": ["quorum"],
    "PV-06": ["ordre_du_jour"],
    "PV-07": ["deliberations_adoptees"],
    "PV-08": ["rapports_cites"],
    "PV-09": ["scrutin_particulier_demande"],   # voir DN-27 (valeur "aucune_demande")
    "PV-10": ["resultat_scrutins"],
    "PV-11": ["teneur_discussions"],
    "PV-12": ["signature_ou_mention_signe"],
}
# Obligations de séance lues sur une pièce de type précis
FAITS_AUTRES = {
    "VS-01": ("PV", ["quorum_atteint"]),
    "VS-07": ("DELIB", ["signature", "numero_deliberation"]),
}
AUCUNE_DEMANDE = "aucune_demande"


@dataclass
class Fait:
    cle: str
    valeur: object                  # True / False / None / "aucune_demande"
    douteux: bool = False
    tranche: Optional[bool] = None  # décision humaine (passe 3) : prime sur la valeur si présente


@dataclass
class Piece:
    type: str                       # sortie de typage.typer
    douteux_type: bool = False      # typage douteux, non tranché par un humain
    publie_le: Optional[date] = None
    faits: Dict[str, Fait] = field(default_factory=dict)


def _etat_fait(f: Optional[Fait]):
    """-> True / False / None (inconnu ou douteux, donc « à vérifier »)."""
    if f is None:
        return None
    if f.tranche is not None:
        return f.tranche
    if f.douteux or f.valeur is None:
        return None
    return f.valeur


def resultat_faits(faits: Dict[str, Fait], cles: List[str]) -> str:
    """Tous vrais : oui ; un faux établi : non ; sinon à vérifier. « aucune_demande » : non applicable (DN-27)."""
    etats = []
    for k in cles:
        f = faits.get(k)
        if f is not None and f.valeur == AUCUNE_DEMANDE and f.tranche is None and not f.douteux:
            return NA
        etats.append(_etat_fait(f))
    if any(e is False for e in etats):
        return NON
    if any(e is None for e in etats):
        return AV
    return OUI


def construire_seance(d: date, pieces: List[Piece], attendue: bool = False,
                      catalogue=None, numeros_attendus: Optional[Set[int]] = None,
                      numeros_trouves: Optional[Set[int]] = None) -> Seance:
    """Construit la Seance du moteur à partir des pièces typées et de leurs faits."""
    cat = catalogue or charger_catalogue()
    s = Seance(date=d, attendue=attendue)
    douteux_docs: Set[str] = set()
    pieces_par_doc: Dict[str, List[Piece]] = {}
    for p in pieces:
        doc = TYPE_VERS_DOC.get(p.type)
        if doc is None:
            continue
        pieces_par_doc.setdefault(doc, []).append(p)
    for doc, ps in pieces_par_doc.items():
        sures = [p for p in ps if not p.douteux_type]
        if sures:
            s.docs.add(doc)
        else:                                  # seules des pièces au type douteux : présence à vérifier (P57)
            s.docs.add(doc)
            douteux_docs.add(doc)

    # Pièce de type indéterminé (ex. liste des délibérations ou ordre du jour, date manquante) : on ne sait pas
    # quel document elle atteste. Pour chaque document non attesté avec certitude, l'existence devient
    # « à vérifier » (jamais « non » sur une pièce que l'on n'a pas su typer, P57, DN-29).
    if any(p.type == "INCONNU" and p.douteux_type for p in pieces):
        for doc in ("PV", "DELIB", "LISTE"):
            if doc not in s.docs:
                s.docs.add(doc)
                douteux_docs.add(doc)

    for o in cat.values():
        if o.document in douteux_docs and o.occurrence in ("par séance", "par PV"):
            s.resultats[o.id] = AV
    # Faits des PV (PV-01..PV-12, VS-01) : on prend le PV sûr, sinon rien (reste « à vérifier » par défaut du moteur)
    for oid, cles in FAITS_PV.items():
        s.resultats.setdefault(oid, _sur_pieces(pieces_par_doc.get("PV", []), cles))
    for oid, (doc, cles) in FAITS_AUTRES.items():
        s.resultats.setdefault(oid, _sur_pieces(pieces_par_doc.get(doc, []), cles))
    # ACT-001-E, ACT-002-E, ACT-003-E : existence ; le moteur met « non » si la pièce est absente (P47)
    for oid, doc in (("ACT-001-E", "DELIB"), ("ACT-002-E", "PV"), ("ACT-003-E", "LISTE")):
        if doc in pieces_par_doc and doc not in douteux_docs:
            s.resultats.setdefault(oid, OUI)
    # ACT-001-E / ACT-001-T : principe aucune / certaines / toutes (DN-57), si l'on connaît la liste des délibérations attendues
    if numeros_trouves is not None and "DELIB" not in douteux_docs:
        e, t = aucune_certaines_toutes(numeros_attendus, numeros_trouves)
        s.resultats["ACT-001-E"], s.resultats["ACT-001-T"] = e, t
    return s


def _sur_pieces(ps: List[Piece], cles: List[str]) -> str:
    sures = [p for p in ps if not p.douteux_type]
    if not sures:
        return AV
    # plusieurs pièces du même type : on fusionne leurs faits (le fait le plus favorable ne masque pas un doute)
    faits: Dict[str, Fait] = {}
    for p in sures:
        for k, f in p.faits.items():
            if k not in faits or (_etat_fait(faits[k]) is None and _etat_fait(f) is not None):
                faits[k] = f
    return resultat_faits(faits, cles)


# ---- Règles qui portent sur plusieurs séances ou plusieurs passages ----

def delai_pv(seances: List[Seance], publications_pv: Dict[date, Optional[date]]) -> None:
    """ACT-002-D : oui si publié au plus tard 7 jours après la séance suivante (N+1) ; non sinon.
    publications_pv : date de séance -> date de publication du PV (date écrite P40c ; None = inconnue).
    La dernière séance n'est pas jugée (P55). Pièce absente : le moteur met « non » (P47)."""
    ordre = sorted((s for s in seances if not s.attendue), key=lambda s: s.date)
    for i, s in enumerate(ordre[:-1]):
        suivante = ordre[i + 1]
        pub = publications_pv.get(s.date)
        if "PV" not in s.docs:
            continue
        if pub is None:
            s.resultats["ACT-002-D"] = AV
        else:
            s.resultats["ACT-002-D"] = OUI if pub <= suivante.date + timedelta(days=7) else NON


def existence_pv_par_contenu(resultats: Dict[str, str]) -> str:
    """ACT-002-E par le contenu (DN-63, arbitrage du 27/10/2026) : un document publié qui remplit toutes les mentions
    d'un procès-verbal (PV-01 à PV-12) vaut procès-verbal, même intitulé « extrait » ou « compte rendu ».
    Une mention non applicable (aucune demande de scrutin) ne compte pas ; un « non » établi : non ; un doute : à vérifier."""
    etats = [resultats.get(k, AV) for k in FAITS_PV if resultats.get(k, AV) != NA]
    if any(e == NON for e in etats):
        return NON
    if any(e == AV for e in etats):
        return AV
    return OUI


def deliberations_completes(numeros_attendus: Optional[Set[int]], numeros_trouves: Set[int]) -> str:
    """ACT-001-T (P60) : toutes les délibérations numérotées dans l'ordre du jour ou le PV sont retrouvées."""
    if not numeros_attendus:
        return AV
    return OUI if numeros_attendus <= numeros_trouves else NON


def aucune_certaines_toutes(numeros_attendus: Optional[Set[int]], numeros_trouves: Set[int]) -> tuple:
    """Principe général « aucune / certaines / toutes » (DN-57, arbitrage du 23/10/2026), en deux obligations binaires :
    - (existence) au moins un élément publié : oui ; aucun : non ;
    - (complétude) tous les éléments attendus publiés : oui ; sinon non.
    aucune -> (non, non) ; certaines -> (oui, non) ; toutes -> (oui, oui).
    Sans liste de référence des éléments attendus, la complétude est « à vérifier » (jamais « non » sur une simple absence de référence)."""
    existence = OUI if numeros_trouves else NON
    if not numeros_attendus:
        return existence, AV
    if not numeros_trouves & numeros_attendus:
        return NON, NON
    return OUI, (OUI if numeros_attendus <= numeros_trouves else NON)


def maintien(publie_le: Optional[date], observations: List[tuple], delai_jours: int = 61) -> str:
    """ACT-001-M / P54 : un document publié doit rester en ligne 2 mois (archivage).
    observations : liste (date_du_passage, present: bool).
    - jamais observé : non (DN-07, arbitrage du 23/10/2026)
    - observé puis absent avant la fin du délai : non
    - observé jusqu'à la fin du délai : oui
    - observé mais fenêtre d'observation trop courte pour conclure : à vérifier (DN-28)"""
    obs = sorted(observations)
    vus = [d for d, p in obs if p]
    if not vus:
        return NON          # DN-07 (arbitrage du 23/10/2026) : jamais observé = « non »
    debut = publie_le or vus[0]
    fin_delai = debut + timedelta(days=delai_jours)
    premiere_vue = vus[0]
    for d, p in obs:
        if d > premiere_vue and not p and d <= fin_delai:
            return NON
    if any(d >= fin_delai and p for d, p in obs):
        return OUI
    return AV
