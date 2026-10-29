"""Rapport d'avancement lisible par un humain, régénéré toutes les 6 h par .github/workflows/rapport.yml.
Lit etat/statut.json et manifeste.jsonl, écrit RAPPORT.md (affiché depuis le README). Aucun envoi, aucune notification."""
from __future__ import annotations
import argparse, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def heure(v):
    if not v:
        return "—"
    return datetime.fromisoformat(v).astimezone(PARIS).strftime("%d/%m à %H h %M")


def il_y_a(v, maintenant):
    if not v:
        return ""
    h = (maintenant - datetime.fromisoformat(v)).total_seconds() / 3600
    return f" (il y a {h:.0f} h)" if h >= 1 else " (il y a moins d'une heure)"


def construire(etat: dict, lignes: list[dict], maintenant: datetime) -> str:
    from surveillance import diagnostiquer
    anomalies, _ = diagnostiquer(etat, maintenant)
    p = etat.get("passage_en_cours") or {}
    if anomalies:
        verdict = "🔴 **Attention** : " + " ".join(anomalies)
    elif p and not p.get("termine"):
        verdict = "🟡 **Collecte en cours**, tout se passe normalement."
    else:
        verdict = "🟢 **Tout va bien** : le dernier passage s'est terminé sans erreur."

    par_coll = defaultdict(lambda: {"docs": set(), "pages": set(), "ko": set(), "nouveaux": set(), "taille": 0})
    dernier = max((l["passage"] for l in lignes), default=None)
    for l in lignes:
        c = par_coll[l["collectivite"]]
        u = l["url"]
        if l["statut"] == "present":
            if l.get("est_document"):
                if u not in c["docs"]:
                    c["taille"] += l.get("taille") or 0
                c["docs"].add(u)
                if l.get("premiere_capture") == l["passage"] == dernier:
                    c["nouveaux"].add(u)
            else:
                c["pages"].add(u)
        elif l["statut"] == "non_constatable":
            c["ko"].add(u)

    t = ["# Rapport du robot de collecte", "",
         f"*Mis à jour automatiquement toutes les 6 h — dernière mise à jour le {heure(maintenant.isoformat())} (heure de Paris).*", "",
         verdict, "",
         "| | |", "|---|---|",
         f"| Dernier passage complet | {heure(etat.get('dernier_passage_complet'))}{il_y_a(etat.get('dernier_passage_complet'), maintenant)} |",
         f"| Dernière activité | {heure(etat.get('derniere_observation'))}{il_y_a(etat.get('derniere_observation'), maintenant)} |",
         f"| Passage en cours | {'terminé' if p.get('termine') else 'en cours'} — {len(p.get('collectivites_terminees', []))} collectivité(s) traitée(s) |",
         f"| Erreurs récentes | {len(etat.get('erreurs', []))} |", "",
         "## Par collectivité", "",
         "| Collectivité | Documents trouvés | Nouveaux au dernier passage | Pages lues | Liens inaccessibles | Volume |",
         "|---|---:|---:|---:|---:|---:|"]
    for nom in sorted(par_coll):
        c = par_coll[nom]
        t.append(f"| {nom} | {len(c['docs'])} | {len(c['nouveaux'])} | {len(c['pages'])} | {len(c['ko'])} | {c['taille']/1e6:.0f} Mo |")
    erreurs = etat.get("erreurs", [])[-5:]
    if erreurs:
        t += ["", "## Dernières erreurs", ""] + [f"- {e.get('collectivite')} — {e.get('etape')} : {e.get('message', '')}" for e in erreurs]
    t += ["", "*« Liens inaccessibles » : adresses que le robot n'a pas pu ouvrir (page supprimée, site lent…). Ce n'est pas une panne du robot.*", ""]
    return "\n".join(t)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--etat", default="etat/statut.json"); ap.add_argument("--manifeste", default="manifeste.jsonl")
    ap.add_argument("--sortie", default="RAPPORT.md")
    a = ap.parse_args()
    try:
        etat = json.load(open(a.etat, encoding="utf-8"))
    except (OSError, ValueError):
        etat = {}
    lignes = []
    try:
        for l in open(a.manifeste, encoding="utf-8"):
            try:
                lignes.append(json.loads(l))
            except ValueError:
                pass
    except OSError:
        pass
    texte = construire(etat, lignes, datetime.now(timezone.utc))
    open(a.sortie, "w", encoding="utf-8").write(texte)
    print(texte)
