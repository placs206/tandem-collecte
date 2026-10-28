"""Lance un passage de collecte pour chaque collectivité de config/collectivites.json.

Usage : python run_collecte.py [--archive DIR] [--manifeste FICHIER] [--seulement ID] [--delai S]
Écrit un manifeste JSONL : une ligne par observation, avec la date de première capture (preuve de
publication tardive, P40c/V13/V21). Les octets des documents ne sont jamais modifiés (DN-32).
"""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone
from collecte import Config, DepotFichiers, Navigateur, decouvrir_wp_media, parcourir


def charger_premieres_captures(manifeste: str) -> dict:
    vu = {}
    if os.path.exists(manifeste):
        with open(manifeste, encoding="utf-8") as f:
            for l in f:
                o = json.loads(l)
                if o.get("sha256"):
                    vu.setdefault((o["collectivite"], o["url"], o["sha256"]), o["premiere_capture"])
    return vu


def passage(cfg_json: dict, archive: str, manifeste: str, seulement=None, delai=2.0, parcourir_fn=parcourir, duree_max=0.0) -> int:
    contact = cfg_json.get("contact_robot", "")
    if "A RENSEIGNER" in contact:
        raise SystemExit("Renseigner 'contact_robot' dans config/collectivites.json avant de lancer (DN-10).")
    premieres = charger_premieres_captures(manifeste)
    maintenant = datetime.now(timezone.utc).isoformat()
    n = 0
    with open(manifeste, "a", encoding="utf-8") as sortie:
        for c in cfg_json["collectivites"]:
            if seulement and c["id"] != seulement:
                continue
            conf = Config(user_agent=f"TandemScoreCitoyenBot/0.1 (+contact: {contact})", delai=delai, duree_max=duree_max, verbeux=True,
                          hotes_autorises=set(c.get("hotes_autorises", [])))
            depot = DepotFichiers(os.path.join(archive, c["id"]))
            def ecrire(o, coll=c):
                nonlocal n
                prem = premieres.get((coll["id"], o.url, o.sha256), maintenant) if o.sha256 else None
                sortie.write(json.dumps({
                    "collectivite": coll["id"], "passage": maintenant, "url": o.url, "page_hote": o.page_hote,
                    "statut": o.statut, "raison": o.raison, "sha256": o.sha256, "mime": o.mime,
                    "taille": o.taille, "est_document": o.est_document, "premiere_capture": prem,
                    "depose_le_site": o.depose_le_site}, ensure_ascii=False) + "\n")
                sortie.flush()
                n += 1
            conf.sur_observation = ecrire
            try:
                for o in parcourir_fn(c["points_entree"], depot, conf):
                    pass                        # déjà écrit au fil de l'eau par le rappel
            except Exception as e:          # une collectivité en panne ne doit jamais arrêter les autres
                print(f"ERREUR {c['id']} parcours : {type(e).__name__} {e}", flush=True)
            for base in c.get("wp_media", []):
                try:
                    for o in decouvrir_wp_media(base, c.get("wp_termes", ["conseil"]), depot, Navigateur(conf),
                                                duree_max=duree_max, pages_max=c.get("wp_pages", 3),
                                                filtre=c.get("wp_filtre", "")):
                        ecrire(o)
                except Exception as e:
                    print(f"ERREUR {c['id']} api média : {type(e).__name__} {e}", flush=True)
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/collectivites.json")
    ap.add_argument("--archive", default="archive")
    ap.add_argument("--manifeste", default="manifeste.jsonl")
    ap.add_argument("--seulement")
    ap.add_argument("--delai", type=float, default=2.0)
    ap.add_argument("--duree-max", type=float, default=0.0, help="secondes par collectivité")
    a = ap.parse_args()
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    print(passage(cfg, a.archive, a.manifeste, a.seulement, a.delai, duree_max=a.duree_max), "observations")
