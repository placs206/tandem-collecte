"""Découpe l'ancien manifeste.jsonl (un seul fichier, bientôt au-delà des 100 Mo acceptés par GitHub : anomalie A-03)
en un fichier par collectivité et par passage : manifeste/<collectivité>/<passage>.jsonl.

- Chaque ligne est recopiée telle quelle, octet pour octet, dans l'ordre d'origine ; rien n'est perdu ni modifié.
- Vérification avant suppression : nombre de lignes et empreinte sha256 de l'ensemble identiques ; sinon arrêt, l'ancien
  fichier est conservé.
- Sans effet si l'ancien fichier n'existe plus (peut être lancé à chaque collecte).
- Une ligne illisible (coupée par un arrêt brutal) va dans manifeste/_illisibles.jsonl : conservée, jamais perdue.
Usage : python scripts/decouper_manifeste.py [manifeste.jsonl] [manifeste]"""
from __future__ import annotations
import hashlib, json, os, sys


def nom_fichier(dossier: str, collectivite: str, passage: str) -> str:
    return os.path.join(dossier, collectivite, passage.replace(":", "-") + ".jsonl")


def decouper(source: str = "manifeste.jsonl", dossier: str = "manifeste") -> int:
    if not os.path.isfile(source):
        print(f"{source} absent : rien à découper.")
        return 0
    with open(source, "rb") as f:
        lignes = [l for l in f.read().split(b"\n") if l.strip()]
    sorties: dict = {}
    for l in lignes:
        try:
            o = json.loads(l)
            chemin = nom_fichier(dossier, o["collectivite"], o["passage"])
        except (ValueError, KeyError, TypeError):
            chemin = os.path.join(dossier, "_illisibles.jsonl")
        sorties.setdefault(chemin, []).append(l)
    deja = [c for c in sorties if os.path.exists(c)]
    if deja:
        raise SystemExit(f"ARRÊT : {len(deja)} fichier(s) existent déjà dans {dossier}/ (ex. {deja[0]}). Rien n'a été modifié.")
    for chemin, ls in sorties.items():
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "xb") as f:
            f.write(b"\n".join(ls) + b"\n")
    # vérification : mêmes lignes, même ordre à l'intérieur de chaque fichier, même empreinte de l'ensemble
    relues = []
    for chemin in sorties:
        with open(chemin, "rb") as f:
            relues += [l for l in f.read().split(b"\n") if l.strip()]
    empreinte = lambda ls: hashlib.sha256(b"\n".join(sorted(ls))).hexdigest()
    if len(relues) != len(lignes) or empreinte(relues) != empreinte(lignes):
        raise SystemExit("ARRÊT : la vérification a échoué ; l'ancien fichier est conservé.")
    os.remove(source)
    print(f"{len(lignes)} lignes réparties dans {len(sorties)} fichiers sous {dossier}/ ; vérification OK ; {source} supprimé.")
    return len(lignes)


if __name__ == "__main__":
    decouper(*(sys.argv[1:3]))
