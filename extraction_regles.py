"""Passe 1 d'extraction : règles fixes (spécification section 3.1, DN-14).

Une règle ne produit un fait que si elle trouve une formule sans ambiguïté (valeur True, confiance haute).
Quand elle ne trouve rien, le fait est « non trouvé » (valeur None) et part en passe 2 (IA) : une règle fixe
ne conclut JAMAIS « non » à elle seule (un oubli de la règle n'est pas un manquement de la collectivité).
Chaque règle a un identifiant et une version.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, Optional

from constats import Fait
from typage import normaliser

VERSION_REGLES = "extraction-regles-0.1"
MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}

_R_DATE_LETTRES = re.compile(r"(?:seance|reunion|conseil) (?:municipal |communautaire |metropolitain )?(?:du|le)\s+"
                             r"(\d{1,2}|1er)\s+(" + "|".join(MOIS) + r")\s+(20\d{2})")
_R_DATE_NUM = re.compile(r"(?:seance|reunion|conseil)[^.\n]{0,40}?(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})")
_R_HEURE = re.compile(r"\b([01]?\d|2[0-3])\s?(?:h|heures?|:)\s?([0-5]\d)?\b")
_R_PRESIDENT = re.compile(r"(sous la presidence de|presidee? par|presidence de|president de seance)\s+\w+")
_R_PRESENTS = re.compile(r"(?:membres |conseillers )?presents?(?: ou representes)?\s*:\s*\S+")
_R_SECRETAIRE = re.compile(r"secretaires? de seance\s*(?::|est|a ete|,)?\s*\w+|secretaire\s*:\s*\w+|"
                           r"(?:designe|nomme|elu)e? (?:en qualite de )?secretaire")
_R_QUORUM = re.compile(r"quorum (?:est |etant |ayant ete )?(?:atteint|constate)|"
                       r"(?:peut|pouvait) valablement deliberer|conditions de quorum")
_R_ODJ = re.compile(r"ordre du jour")
_R_ADOPTE = re.compile(r"(?:est |sont |a ete |ont ete )?(?:adopte|approuve|vote)e?s?\b|a l'unanimite|"
                       r"apres en avoir delibere")
_R_RAPPORT = re.compile(r"(?:au vu du|vu le|sur le|expose du|presente le|selon le)\s+rapport|rapporteur|"
                        r"rapport (?:de|du|presente par|expose)")
_R_SCRUTIN_DEMANDE = re.compile(r"(?:demande|demandee?s?|sollicite|requis)[^.\n]{0,60}scrutin (?:public|secret)|"
                                r"scrutin (?:public|secret)[^.\n]{0,60}(?:demande|demandee?s?|sollicite|requis)")
_R_AUCUNE_DEMANDE = re.compile(r"aucune demande de scrutin|pas de demande de scrutin|"
                               r"aucun (?:membre|conseiller) n'a demande (?:le |de )?scrutin")
_R_RESULTAT = re.compile(r"\bpour\s*:?\s*\d+|\bcontre\s*:?\s*\d+|abstentions?\s*:?\s*\d+|a l'unanimite|"
                         r"\d+\s+voix|\d+\s+(?:pour|contre|abstentions?)")
_R_DISCUSSION = re.compile(r"(?:prend la parole|intervient|souligne|rappelle|s'interroge|precise que|"
                           r"fait observer|apres discussion|apres debat|les debats|debat portant)")
_R_SIGNE = re.compile(r"\bsigne\b|\(signe\)|signe electroniquement|le maire,?\s+[a-z]|le president,?\s+[a-z]")
_R_NUMERO = re.compile(r"deliberation\s*n[o°º]?\s*[:.]?\s*(\d{1,4}(?:[-/]\d{1,4})?)|n[o°º]\s*(\d{4}[-/]\d{1,4})")


def _fait(cle: str, trouve: bool, detail: Optional[str] = None) -> Fait:
    f = Fait(cle, True if trouve else None)
    f.detail = detail       # type: ignore[attr-defined]  # extrait source (preuve), ajouté dynamiquement
    return f


def extraire_date_seance(t: str) -> Optional[date]:
    m = _R_DATE_LETTRES.search(t)
    if m:
        j = 1 if m.group(1) == "1er" else int(m.group(1))
        try:
            return date(int(m.group(3)), MOIS[m.group(2)], j)
        except ValueError:
            return None
    m = _R_DATE_NUM.search(t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def extraire_pv(texte: str) -> Dict[str, Fait]:
    t = normaliser(texte)
    faits: Dict[str, Fait] = {}
    d = extraire_date_seance(t)
    faits["seance_date"] = _fait("seance_date", d is not None, d.isoformat() if d else None)
    debut = t[:1500]
    h = _R_HEURE.search(debut)
    faits["heure"] = _fait("heure", bool(h), h.group(0) if h else None)
    for cle, rx in (("president", _R_PRESIDENT), ("presents", _R_PRESENTS), ("secretaire", _R_SECRETAIRE),
                    ("quorum", _R_QUORUM), ("ordre_du_jour", _R_ODJ), ("rapports_cites", _R_RAPPORT)):
        m = rx.search(t)
        faits[cle] = _fait(cle, bool(m), m.group(0) if m else None)
    faits["quorum_atteint"] = Fait("quorum_atteint", faits["quorum"].valeur)
    m = _R_ADOPTE.search(t)
    faits["deliberations_adoptees"] = _fait("deliberations_adoptees", bool(m), m.group(0) if m else None)
    # scrutin particulier : demande consignée, ou « aucune demande » (-> non applicable, DN-27)
    if _R_AUCUNE_DEMANDE.search(t):
        faits["scrutin_particulier_demande"] = Fait("scrutin_particulier_demande", "aucune_demande")
    else:
        m = _R_SCRUTIN_DEMANDE.search(t)
        faits["scrutin_particulier_demande"] = _fait("scrutin_particulier_demande", bool(m),
                                                      m.group(0) if m else None)
    m = _R_RESULTAT.search(t)
    faits["resultat_scrutins"] = _fait("resultat_scrutins", bool(m), m.group(0) if m else None)
    n_disc = len(_R_DISCUSSION.findall(t))
    faits["teneur_discussions"] = _fait("teneur_discussions", n_disc >= 2, f"{n_disc} marques de discussion")
    fin = t[-800:]
    m = _R_SIGNE.search(fin)
    faits["signature_ou_mention_signe"] = _fait("signature_ou_mention_signe", bool(m), m.group(0) if m else None)
    return faits


def extraire_registre(texte: str) -> Dict[str, Fait]:
    t = normaliser(texte)
    m = _R_NUMERO.search(t)
    s = _R_SIGNE.search(t[-800:])
    return {"numero_deliberation": _fait("numero_deliberation", bool(m), m.group(0) if m else None),
            "signature": _fait("signature", bool(s), s.group(0) if s else None)}


def extraire(type_piece: str, texte: str) -> Dict[str, Fait]:
    if type_piece == "PV":
        return extraire_pv(texte)
    if type_piece in ("EXTRAIT_REGISTRE", "DELIB"):
        return extraire_registre(texte)
    return {}
