"""Règles d'affichage des noms de personnes (arbitrage du 23/10/2026, DN-32 à DN-35).

- Les copies archivées ne sont JAMAIS modifiées (règle d'or : la preuve est centrale) ; ces règles
  ne s'appliquent qu'à ce que le site affiche et à la base ouverte.
- Élu ou agent identifié : civilité (si la source la donne) + « initiale du prénom + NOM »
  (ex. « Mme C. DUPONT », « M. C. DUPONT »), jamais le prénom complet (DN-33, civilité ajoutée DN-35).
  Sans civilité dans la source, on n'en devine pas (pas d'inférence du genre) : « C. DUPONT ».
- Personne privée (habitant, pétitionnaire, tiers) : masquée (« [personne privée] »).
  C'est une réduction du risque, pas une anonymisation : « C. DUPONT » reste identifiable.
"""
from __future__ import annotations

import re
import unicodedata

MASQUE_TIERS = "[personne privée]"
_CIVILITES = r"(?:m\.?|mme\.?|mlle\.?|monsieur|madame|mademoiselle|dr\.?|me\.?|maître)"
_NORMALISE = {"m": "M.", "monsieur": "M.", "mme": "Mme", "madame": "Mme", "mlle": "Mme",
              "mademoiselle": "Mme", "dr": "Dr", "me": "Me", "maître": "Me"}


def _initiale(prenom: str) -> str:
    p = prenom.strip()
    if not p:
        return ""
    # prénom composé (Jean-Pierre) : première lettre du premier élément
    return unicodedata.normalize("NFC", p[0]).upper() + "."


def pseudonymiser_nom(nom_complet: str) -> str:
    """« Madame Claire Dupont » -> « Mme C. DUPONT » ; « Claire Dupont » -> « C. DUPONT » (civilité non devinée).
    Le nom de famille est mis en majuscules ; en cas de doute (un seul mot), on renvoie le NOM seul."""
    m = re.match(rf"^\s*({_CIVILITES})\s+", nom_complet, flags=re.IGNORECASE)
    civilite = _NORMALISE.get(m.group(1).lower().rstrip("."), "") if m else ""
    s = nom_complet[m.end():] if m else nom_complet
    parts = s.split()
    if not parts:
        return ""
    if len(parts) == 1:
        return f"{civilite} {parts[0].upper()}".strip()
    # convention : prénom(s) puis NOM ; si le premier mot est tout en majuscules, c'est « NOM Prénom »
    if parts[0].isupper() and len(parts[0]) > 2 and not parts[-1].isupper():
        nom, prenom = parts[0], parts[1]
    else:
        nom, prenom = parts[-1], parts[0]
    ini = _initiale(prenom)
    return f"{civilite} {ini} {nom.upper()}".strip()


def afficher_personne(nom_complet: str, est_elu_ou_agent: bool) -> str:
    """Seuls les élus et agents dans l'exercice de leur fonction apparaissent (sous forme abrégée)."""
    return pseudonymiser_nom(nom_complet) if est_elu_ou_agent else MASQUE_TIERS


# ---- Personnes privées : un repère stable par collectivité (DN-36, DN-37) ----
# Le citoyen voit « [personne privée A] » ; il est averti quand la même personne revient souvent
# (conflit d'intérêts possible) ; pour vérifier, il ouvre le document source archivé, intact, où le nom figure.
# Le nom ne quitte jamais la table privée : seules les citations (repère + document) sont publiques.
from dataclasses import dataclass, field  # noqa: E402
from typing import Dict, List, Set, Tuple  # noqa: E402

SEUIL_SIGNALEMENT = 3   # nombre de documents distincts à partir duquel le citoyen est averti (DN-37, validé le 23/10/2026)


def lettre(n: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, 27 -> AB ..."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cle(nom_complet: str) -> frozenset:
    """Clé d'identité : mots du nom sans civilité, sans accent, sans casse, ordre indifférent."""
    sans = re.sub(rf"^\s*{_CIVILITES}\s+", "", nom_complet, flags=re.IGNORECASE)
    sans = unicodedata.normalize("NFD", sans)
    sans = "".join(c for c in sans if unicodedata.category(c) != "Mn").lower()
    return frozenset(t for t in re.split(r"[\s\-'.]+", sans) if t)


@dataclass
class RegistrePersonnes:
    """Un registre PAR collectivité : la même personne y reçoit toujours la même lettre."""
    collectivite_id: str
    _reperes: Dict[frozenset, str] = field(default_factory=dict)
    _noms: Dict[str, str] = field(default_factory=dict)             # repère -> nom (PRIVÉ, jamais exporté)
    _citations: Dict[str, Set[Tuple[int, int]]] = field(default_factory=dict)  # repère -> {(document_id, page)}

    def repere(self, nom_complet: str, document_id: int, page: int = 0) -> str:
        cle = _cle(nom_complet)
        if cle not in self._reperes:
            self._reperes[cle] = lettre(len(self._reperes))
            self._noms[self._reperes[cle]] = nom_complet.strip()
        r = self._reperes[cle]
        self._citations.setdefault(r, set()).add((document_id, page))
        return f"[personne privée {r}]"

    def signalements(self, seuil: int = SEUIL_SIGNALEMENT) -> List[dict]:
        """Bloc PUBLIC de la fiche : repère, nombre de documents distincts, documents sources. Sans nom."""
        out = []
        for r, cites in self._citations.items():
            docs = sorted({d for d, _ in cites})
            if len(docs) >= seuil:
                out.append({"repere": f"[personne privée {r}]", "nb_documents": len(docs), "documents": docs})
        return sorted(out, key=lambda x: (-x["nb_documents"], x["repere"]))

    def rapprochements_possibles(self) -> List[Tuple[str, str]]:
        """Pour la relecture humaine : « C. Dupont » et « Claire Dupont » sont peut-être la même personne
        (jamais fusionnées automatiquement : une fusion fausse accuserait deux personnes d'être une seule)."""
        paires = []
        items = list(self._reperes.items())
        for i, (c1, r1) in enumerate(items):
            for c2, r2 in items[i + 1:]:
                for petit, grand in ((c1, c2), (c2, c1)):
                    inis = {t for t in petit if len(t) == 1}
                    reste = petit - inis
                    if inis and reste and reste <= grand and all(
                            any(g.startswith(i2) for g in grand - reste) for i2 in inis):
                        paires.append((f"[personne privée {r1}]", f"[personne privée {r2}]"))
                        break
        return paires
