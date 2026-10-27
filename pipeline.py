"""Chaîne complète d'une séance : texte des pièces -> typage -> faits (passe 1) -> constats -> moteur.

Les faits non trouvés par les règles restent « à vérifier » (la passe 2, IA, et la passe 3, relecture humaine,
les compléteront) : le calcul ne devine jamais.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from constats import Piece, construire_seance
from engine import Seance
from extraction_regles import extraire
from typage import Typage, typer


@dataclass
class PieceBrute:
    texte: str
    titre: str = ""
    nom_fichier: str = ""
    date_piece: Optional[date] = None
    publie_le: Optional[date] = None
    type_tranche: Optional[str] = None      # type décidé par un relecteur humain (prime sur le typage)


def traiter_seance(date_seance: date, pieces: List[PieceBrute], attendue: bool = False) -> tuple:
    """Retourne (Seance du moteur, liste de cas douteux à relire)."""
    prets: List[Piece] = []
    douteux: List[dict] = []
    for i, p in enumerate(pieces):
        if p.type_tranche:
            ty = Typage(p.type_tranche, 1.0, False, ["tranché par un relecteur"])
        else:
            ty = typer(p.texte, p.titre, p.nom_fichier, p.date_piece, date_seance)
        if ty.douteux:
            douteux.append({"piece": i, "motif": "type douteux", "type": ty.type, "raisons": ty.raisons})
        faits = extraire(ty.type, p.texte) if not ty.douteux else {}
        non_trouves = [k for k, f in faits.items() if f.valeur is None]
        if non_trouves:
            douteux.append({"piece": i, "motif": "faits non trouvés par les règles (passe 2)", "faits": non_trouves})
        prets.append(Piece(ty.type, douteux_type=ty.douteux, publie_le=p.publie_le, faits=faits))
    return construire_seance(date_seance, prets, attendue), douteux
