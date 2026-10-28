"""Veille du robot : lit etat/statut.json (écrit par run_collecte) et dit s'il y a anomalie.
Anomalies : aucune réussite complète depuis plus de 36 h ; passage interrompu sans progrès depuis plus de 12 h ;
erreurs récentes. Écrit diagnostic.md et les sorties alerte=oui|non, relancer=oui|non."""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timedelta, timezone


def diagnostiquer(etat: dict, maintenant: datetime, retard_h=36.0, sans_progres_h=12.0):
    anomalies = []
    def age(k):
        v = etat.get(k)
        return maintenant - datetime.fromisoformat(v) if v else None
    reussite = age("dernier_passage_complet")
    if reussite is None:
        anomalies.append("Aucun passage complet n'est encore enregistré.")
    elif reussite > timedelta(hours=retard_h):
        anomalies.append(f"Dernier passage complet il y a {reussite.total_seconds()/3600:.0f} h (seuil {retard_h:.0f} h).")
    p = etat.get("passage_en_cours")
    prog = age("derniere_observation")
    if p and not p.get("termine") and prog is not None and prog > timedelta(hours=sans_progres_h):
        anomalies.append(f"Passage en cours sans progression depuis {prog.total_seconds()/3600:.0f} h.")
    rec = age("derniere_erreur")
    if rec is not None and rec < timedelta(hours=6):
        anomalies.append("Erreurs récentes : " + "; ".join(f"{e['collectivite']} {e['etape']}" for e in etat.get("erreurs", [])[-3:]))
    relancer = bool(anomalies) and (reussite is None or reussite > timedelta(hours=retard_h))
    return anomalies, relancer


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--etat", default="etat/statut.json"); ap.add_argument("--sortie")
    a = ap.parse_args()
    try:
        etat = json.load(open(a.etat, encoding="utf-8"))
    except (OSError, ValueError):
        etat = {}
    anomalies, relancer = diagnostiquer(etat, datetime.now(timezone.utc))
    texte = ("Anomalie(s) :\n- " + "\n- ".join(anomalies)) if anomalies else "Tout va bien : dernier passage complet " + str(etat.get("dernier_passage_complet"))
    texte += f"\n\nDernière observation : {etat.get('derniere_observation')}\nDernière exécution : {etat.get('derniere_execution')}\n"
    open("diagnostic.md", "w", encoding="utf-8").write(texte)
    print(texte)
    if a.sortie:
        with open(a.sortie, "a") as f:
            f.write(f"alerte={'oui' if anomalies else 'non'}\nrelancer={'oui' if relancer else 'non'}\n")
