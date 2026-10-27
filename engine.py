"""Moteur de calcul de la note (v0.1, 22/10/2026).

Déterministe, sans IA. Entrées : une collectivité, ses séances, les constats déjà établis.
Règles implémentées : D13 (obligations binaires, aucune pondération), P10 (24 mois), P27 (compétence transférée),
P41 (toutes les séances comptent), P47 (document absent = non), P53 (conditionnel : compté seulement si fait établi),
P54 (maintien : « non » si document jamais observé, DN-07 arbitré le 23/10/2026), P55 (PV compté
quand la séance suivante a eu lieu), P56 (séance attendue par trimestre sans document), P57 (a_verifier non compté).
"""
from __future__ import annotations
import csv, os
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

OUI, NON, NA, AV = "oui", "non", "non_applicable", "a_verifier"
HERE = os.path.dirname(os.path.abspath(__file__))
SEANCE_DOCS = {"PV", "DELIB", "LISTE"}
# obligations évaluées une fois par séance (les autres : trimestre, exercice, année ou événement)
PAR_SEANCE = {"par séance", "par PV"}
COMPETENCE = {"SPL-003-E": "dechets", "SPL-010-E": "dechets", "SPL-011-E": "dechets"}
EPCI_TYPES = {"communaute_communes", "communaute_agglomeration", "communaute_urbaine", "metropole"}


@dataclass
class Obligation:
    id: str; libelle: str; axe: str; module: str; occurrence: str; statut: str
    document: str; condition: str


def charger_catalogue(path: str = None) -> Dict[str, Obligation]:
    path = path or os.path.join(HERE, "obligations.csv")
    out = {}
    with open(path, encoding="utf8") as f:
        for r in csv.DictReader(f):
            out[r["id"]] = Obligation(r["id"], r["libelle"], r["axe"], r["module"], r["occurrence"],
                                      r["statut"], r["document"], r["condition"])
    return out


@dataclass
class Collectivite:
    type: str
    population: int
    faits: Set[str] = field(default_factory=set)         # faits publics établis (ex. 'URB-001-E', 'ARRETE_BRUIT')
    competences: Set[str] = field(default_factory=set)   # compétences exercées par cette collectivité (BANATIC)

    @property
    def est_epci(self): return self.type in EPCI_TYPES


@dataclass
class Seance:
    date: date
    attendue: bool = False
    docs: Set[str] = field(default_factory=set)          # pièces publiées trouvées : PV, DELIB, LISTE
    resultats: Dict[str, str] = field(default_factory=dict)  # obligation_id -> oui/non/a_verifier/non_applicable


@dataclass
class Ligne:
    obligation: str; occurrence: str; resultat: str; axe: str


@dataclass
class Note:
    globale: Optional[float]
    oui: int; non: int; a_verifier: int; non_applicable: int
    couverture: float
    axes: Dict[str, dict]
    lignes: List[Ligne]


def applicable(o: Obligation, c: Collectivite) -> bool:
    """Module d'activation (P20 à P22, P27, P53)."""
    if o.statut != "calcule":
        return False
    m, pop, epci = o.module, c.population, c.est_epci
    if o.id in COMPETENCE and COMPETENCE[o.id] not in c.competences:
        return False
    if m == "SOCLE": return True
    if m == "M1000": return epci or pop >= 1000
    if m == "M1000_STRICT": return epci or pop > 1000
    if m == "M2000": return (not epci) and pop > 2000
    if m == "M3500": return pop >= 3500
    if m == "M5000": return pop > 5000
    if m == "M10000": return pop >= 10000
    if m == "M20000": return pop >= 20000
    if m == "M40000": return pop > 40000
    if m == "M50000": return pop > 50000
    if m == "EPCI_20000": return epci and pop > 20000
    if m == "EPCI": return epci
    if m == "EPCI_50000": return epci and pop > 50000
    if m == "EPCI_EVT": return epci
    if m == "ARRETE_BRUIT": return "ARRETE_BRUIT" in c.faits
    if m == "FAIT": return True       # la condition est vérifiée ligne par ligne (fait établi)
    raise ValueError(f"module inconnu : {m}")


def _debut_trimestre_suivant(d0: date) -> date:
    m = d0.month + 3
    return date(d0.year + (m > 12), (m - 1) % 12 + 1, 1)


def trimestres(debut: date, fin: date):
    """Trimestres civils entièrement contenus dans [debut, fin] (début inclus, fin incluse)."""
    out = []
    q0 = (debut.month - 1) // 3 * 3 + 1
    d0 = date(debut.year, q0, 1)
    if d0 < debut:                       # premier trimestre incomplet : on le saute
        d0 = _debut_trimestre_suivant(d0)
    while True:
        d1 = _debut_trimestre_suivant(d0)
        if (d1 - fin).days > 1:          # le trimestre se termine après la fin de fenêtre
            break
        out.append((d0, d1))
        d0 = d1
    return out


def completer_seances(seances: List[Seance], debut: date, fin: date) -> List[Seance]:
    """P56 : pour chaque trimestre complet de la fenêtre sans aucune séance ni document, une séance attendue."""
    res = list(seances)
    for d0, d1 in trimestres(debut, fin):
        if not any(d0 <= s.date < d1 for s in seances):
            res.append(Seance(date=d1, attendue=True))
    return sorted(res, key=lambda s: s.date)


def calculer(c: Collectivite, seances: List[Seance], debut: date, fin: date,
             constats: Optional[Dict[Tuple[str, str], str]] = None,
             catalogue: Optional[Dict[str, Obligation]] = None) -> Note:
    """constats : (obligation_id, clé d'occurrence) -> résultat, pour les obligations hors séance."""
    cat = catalogue or charger_catalogue()
    constats = constats or {}
    seances = [s for s in completer_seances(seances, debut, fin) if debut <= s.date <= fin]
    lignes: List[Ligne] = []
    obs = [o for o in cat.values() if applicable(o, c)]

    for o in obs:
        def add(occ, res): lignes.append(Ligne(o.id, occ, res, o.axe))

        if o.occurrence in PAR_SEANCE:
            for i, s in enumerate(seances):
                occ = s.date.isoformat() + ("*" if s.attendue else "")
                doc = o.document
                suivante = i + 1 < len(seances)
                if doc == "PV" and not suivante:      # P55 : le PV n'est arrêté qu'à la séance suivante
                    continue
                present = (doc in s.docs) if doc in SEANCE_DOCS else (not s.attendue)
                if o.id.endswith("-M"):               # maintien : document absent = « non » (DN-07, arbitrage du 23/10/2026)
                    add(occ, s.resultats.get(o.id, AV) if present else NON); continue
                if o.id.endswith("-D") and not present:   # DN-62 : délai évalué seulement sur les documents publiés
                    continue                              # (l'absence coûte un seul « non », sur l'existence -E)
                if not present:                       # P47, P56
                    add(occ, NON); continue
                add(occ, s.resultats.get(o.id, AV))
        elif o.occurrence == "par trimestre":         # CS-01
            for d0, d1 in trimestres(debut, fin):
                a_seance = any(d0 <= s.date < d1 and not s.attendue for s in seances)
                add(f"{d0.isoformat()}", OUI if a_seance else NON)
        else:
            cles = [(k, v) for (oid, k), v in constats.items() if oid == o.id]
            if o.condition in ("fait", "evenement") or o.module in ("FAIT", "ARRETE_BRUIT", "EPCI_EVT"):
                if o.condition == "fait" and o.id not in c.faits and not cles:
                    continue                          # P53 : fait non établi -> non applicable, non compté
                for k, v in cles or [("", AV)]:
                    add(k, v)
            else:                                     # obligation non conditionnelle : une occurrence par exercice/année
                if cles:
                    for k, v in cles: add(k, v)
                else:                                 # une occurrence « à vérifier » par année de la fenêtre (DN-25)
                    for an in range(debut.year, fin.year + 1): add(str(an), AV)
    return _agreger(lignes)


def _agreger(lignes: List[Ligne]) -> Note:
    def stat(ls):
        oui = sum(l.resultat == OUI for l in ls); non = sum(l.resultat == NON for l in ls)
        av = sum(l.resultat == AV for l in ls); na = sum(l.resultat == NA for l in ls)
        evalu = oui + non
        note = round(100 * oui / evalu, 2) if evalu else None
        cov = round(100 * evalu / (evalu + av), 2) if (evalu + av) else 0.0
        return dict(note=note, oui=oui, non=non, a_verifier=av, non_applicable=na, couverture=cov)
    axes = {}
    for ax in sorted({l.axe for l in lignes}):
        axes[ax] = stat([l for l in lignes if l.axe == ax])
    g = stat(lignes)
    return Note(g["note"], g["oui"], g["non"], g["a_verifier"], g["non_applicable"], g["couverture"], axes, lignes)
