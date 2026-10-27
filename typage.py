"""Typage des pièces (passe 1, règles fixes) : DN-12, DN-13, spécification section 2.

Principe : le contenu prime sur le nom du fichier (le nom n'est qu'un indice faible).
Quand deux types sont plausibles, la date de la pièce par rapport à la séance tranche ;
sans date, le cas est marqué douteux (il part en relecture, DN-14).
Le typage ne produit aucun résultat d'obligation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

VERSION_REGLES = "typage-0.1"

TYPES = ("PV", "EXTRAIT_REGISTRE", "DELIB", "LISTE_DELIB", "ORDRE_DU_JOUR",
         "CONVOCATION", "INCONNU")


def normaliser(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Typage:
    type: str
    confiance: float
    douteux: bool
    raisons: list[str] = field(default_factory=list)
    version: str = VERSION_REGLES


# Indices : (regex sur l'en-tête normalisé, poids). L'en-tête = début du texte + titre.
_ENTETE = 800

# Tolérant : en deux colonnes, le titre est parfois coupé (« EXTRAIT DU REGISTRE / DES / DÉLIBÉRATIONS »)
_R_EXTRAIT = re.compile(r"extrait du registre")
_R_PV = re.compile(r"(?<!approbation du )(?<!approbation des )(proces[- ]verbal (de la seance|du conseil|de seance|de la reunion)|"
                   r"^proces[- ]verbal|compte[- ]rendu integral|proces[- ]verbal)")
_R_PV_NARRATION = re.compile(r"(a ouvert la seance|ouvre la seance|prend la parole|"
                             r"intervient|apres discussion|apres debat|les debats|la seance est levee|"
                             r"l'ordre du jour etant epuise)")
_R_ODJ = re.compile(r"ordre du jour")
# « dûment convoqué » et « date de convocation » figurent dans tout en-tête de séance : ne prouvent rien.
_R_CONVOC = re.compile(r"(vous etes convoque|vous etes prie|vous etes invite|^convocation|^.{0,80}convocation (du|au|a la) conseil)")
_R_LISTE = re.compile(r"liste des deliberations")
_R_LISTE_EXAMINEES = re.compile(r"deliberations (examinees|adoptees|prises)")
_R_DELIB = re.compile(r"deliberation n[o°º]?\s*\d|deliberation numero")
_R_APRES_DELIBERE = re.compile(r"apres en avoir delibere")


def _a_approbation_pv(entete: str) -> bool:
    return bool(re.search(r"approbation (du|des) proces[- ]verbal", entete))


def typer(texte: str, titre: str = "", nom_fichier: str = "",
          date_piece: Optional[date] = None, date_seance: Optional[date] = None) -> Typage:
    """Retourne le type de la pièce, une confiance (0-1) et un drapeau « douteux »."""
    t = normaliser(texte)
    entete = normaliser(titre + " " + t[:_ENTETE])
    nom = normaliser(nom_fichier)
    raisons: list[str] = []
    scores: dict[str, float] = {}

    def ajoute(type_: str, poids: float, raison: str) -> None:
        scores[type_] = scores.get(type_, 0.0) + poids
        raisons.append(f"{type_}+{poids}: {raison}")

    if not t.strip():
        return Typage("INCONNU", 0.0, True, ["texte vide (OCR à tenter)"])

    if _R_EXTRAIT.search(entete):
        ajoute("EXTRAIT_REGISTRE", 0.9, "« extrait du registre des délibérations » en en-tête")
    elif _R_DELIB.search(entete) and _R_APRES_DELIBERE.search(t):
        ajoute("DELIB", 0.8, "délibération numérotée + « après en avoir délibéré »")
    elif _R_APRES_DELIBERE.search(t) and _R_DELIB.search(t):
        ajoute("DELIB", 0.5, "formule de délibération hors en-tête")

    # PV : « procès-verbal » en en-tête, hors formule « approbation du procès-verbal »
    if _R_PV.search(entete) and not _a_approbation_pv(entete[:200]):
        ajoute("PV", 0.6, "« procès-verbal » en en-tête")
        if _R_PV_NARRATION.search(t):
            ajoute("PV", 0.3, "narration de séance (débats, levée de séance)")
    elif _R_PV_NARRATION.search(t) and not _R_ODJ.search(entete):
        ajoute("PV", 0.3, "narration de séance sans en-tête explicite")

    if _R_CONVOC.search(entete):
        ajoute("CONVOCATION", 0.7, "formule de convocation")

    if "EXTRAIT_REGISTRE" in scores and _R_PV_NARRATION.search(t):
        # Cas Salon-de-Provence : l'« extrait » contient aussi des débats et l'approbation du PV précédent.
        raisons.append("extrait du registre contenant une narration de séance : nature à trancher (DN-13, DN-56)")
        scores["EXTRAIT_REGISTRE"] = min(scores["EXTRAIT_REGISTRE"], 0.7)

    liste = bool(_R_LISTE.search(entete))
    odj = bool(_R_ODJ.search(entete)) and "PV" not in scores
    if liste:
        ajoute("LISTE_DELIB", 0.5, "« liste des délibérations » en en-tête")
        if _R_LISTE_EXAMINEES.search(t):
            ajoute("LISTE_DELIB", 0.2, "« délibérations examinées/adoptées »")
    if odj:
        ajoute("ORDRE_DU_JOUR", 0.5, "« ordre du jour » en en-tête")

    # Le nom du fichier est un indice faible (+0.1 seulement, jamais décisif)
    for mot, type_ in (("proces", "PV"), ("pv", "PV"), ("extrait", "EXTRAIT_REGISTRE"),
                       ("odj", "ORDRE_DU_JOUR"), ("ordre", "ORDRE_DU_JOUR"),
                       ("convocation", "CONVOCATION"), ("liste", "LISTE_DELIB")):
        if mot in nom and type_ in scores:
            scores[type_] += 0.1
            raisons.append(f"{type_}+0.1: nom de fichier (indice faible)")
            break

    if not scores:
        return Typage("INCONNU", 0.0, True, ["aucun indice dans l'en-tête ni le texte"])

    # Ambiguïté liste / ordre du jour : la date tranche (DN-12)
    if "LISTE_DELIB" in scores and "ORDRE_DU_JOUR" in scores:
        if date_piece and date_seance:
            gagnant = "ORDRE_DU_JOUR" if date_piece <= date_seance else "LISTE_DELIB"
            perdant = "LISTE_DELIB" if gagnant == "ORDRE_DU_JOUR" else "ORDRE_DU_JOUR"
            scores[gagnant] += 0.4
            scores.pop(perdant)
            raisons.append(f"{gagnant}: tranché par la date de la pièce ({date_piece}) vs séance ({date_seance})")
        else:
            raisons.append("liste/ordre du jour ambigus et date manquante : relecture")
            return Typage("INCONNU", 0.3, True, raisons)

    classes = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    meilleur, score = classes[0]
    confiance = min(score, 1.0)
    douteux = confiance < 0.8
    if len(classes) > 1 and score - classes[1][1] < 0.3:
        douteux = True
        raisons.append(f"deux types plausibles ({classes[0][0]}, {classes[1][0]})")
    # DN-14 : confiance < 0,8 = cas douteux
    return Typage(meilleur, round(confiance, 2), douteux, raisons)


def vaut_pv(type_: str) -> bool:
    """DN-13 : seul un PV vaut procès-verbal ; un extrait du registre n'en est pas un."""
    return type_ == "PV"


def vaut_liste_deliberations(type_: str) -> bool:
    """Un ordre du jour ne vaut pas liste des délibérations (L2121-25)."""
    return type_ == "LISTE_DELIB"
