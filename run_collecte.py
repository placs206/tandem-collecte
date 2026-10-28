"""Lance un passage de collecte pour chaque collectivité de config/collectivites.json.

Usage : python run_collecte.py [--archive DIR] [--manifeste FICHIER] [--seulement ID] [--delai S]
Écrit un manifeste JSONL : une ligne par observation, avec la date de première capture (preuve de
publication tardive, P40c/V13/V21). Les octets des documents ne sont jamais modifiés (DN-32).
"""
from __future__ import annotations
import argparse, json, os, subprocess, time
from datetime import datetime, timedelta, timezone
from collecte import Config, DepotFichiers, Navigateur, decouvrir_wp_media, parcourir


def charger_premieres_captures(manifeste: str) -> dict:
    vu = {}
    if os.path.exists(manifeste):
        with open(manifeste, encoding="utf-8") as f:
            for l in f:
                try:
                    o = json.loads(l)
                except ValueError:
                    continue                # ligne coupée par un arrêt brutal : ignorée
                if o.get("sha256") and o.get("premiere_capture"):
                    vu.setdefault((o["collectivite"], o["url"], o["sha256"]), o["premiere_capture"])
    return vu


def passage(cfg_json: dict, archive: str, manifeste: str, seulement=None, delai=2.0, parcourir_fn=parcourir, duree_max=0.0,
            passage_id=None, deja=None, terminees=None, fin_avant=None, apres_collectivite=None, apres_observation=None,
            erreurs=None) -> int:
    """Un passage. Paramètres de reprise (tous optionnels, comportement inchangé sans eux) :
    passage_id : reprend un passage interrompu (la date de passage et les premières captures restent celles du passage) ;
    deja : ensemble (collectivité, url, sha256, statut) déjà écrit pour ce passage : jamais écrit deux fois ;
    terminees : ensemble d'identifiants de collectivités terminées, complété ici ;
    fin_avant : échéance (time.time()) : on s'arrête proprement avant, sans marquer la collectivité terminée ;
    apres_collectivite(id) / apres_observation() : rappels de sauvegarde ; erreurs : liste complétée des pannes isolées."""
    terminees = terminees if terminees is not None else set()
    deja = deja if deja is not None else set()
    erreurs = erreurs if erreurs is not None else []
    contact = cfg_json.get("contact_robot", "")
    if "A RENSEIGNER" in contact:
        raise SystemExit("Renseigner 'contact_robot' dans config/collectivites.json avant de lancer (DN-10).")
    premieres = charger_premieres_captures(manifeste)
    maintenant = passage_id or datetime.now(timezone.utc).isoformat()
    n = 0
    if os.path.exists(manifeste) and os.path.getsize(manifeste):
        with open(manifeste, "rb+") as f:           # dernier octet : si la ligne a été coupée, on la termine avant d'ajouter
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
    with open(manifeste, "a", encoding="utf-8") as sortie:
        for c in cfg_json["collectivites"]:
            if seulement and c["id"] != seulement:
                continue
            if c["id"] in terminees:
                continue
            reste = (fin_avant - time.time()) if fin_avant else None
            if reste is not None and reste < 60:
                break                       # plus assez de temps : la suite sera reprise au prochain lancement
            duree_c = duree_max if reste is None else (min(duree_max, reste) if duree_max else reste)
            coupe_par_echeance = reste is not None and (not duree_max or reste < duree_max)
            conf = Config(user_agent=f"TandemScoreCitoyenBot/0.1 (+contact: {contact})", delai=delai, duree_max=duree_c, verbeux=True,
                          pages_max=c.get("pages_max", 400), sans_telechargement=tuple(c.get("sans_telechargement", [])),
                          hotes_autorises=set(c.get("hotes_autorises", [])))
            depot = DepotFichiers(os.path.join(archive, c["id"]))
            def ecrire(o, coll=c):
                nonlocal n
                cle = (coll["id"], o.url, o.sha256, o.statut)
                if cle in deja:
                    return
                deja.add(cle)
                prem = premieres.get((coll["id"], o.url, o.sha256), maintenant) if o.sha256 else None
                sortie.write(json.dumps({
                    "collectivite": coll["id"], "passage": maintenant, "url": o.url, "page_hote": o.page_hote,
                    "statut": o.statut, "raison": o.raison, "sha256": o.sha256, "mime": o.mime,
                    "taille": o.taille, "est_document": o.est_document, "premiere_capture": prem,
                    "depose_le_site": o.depose_le_site}, ensure_ascii=False) + "\n")
                sortie.flush()
                n += 1
                if apres_observation:
                    apres_observation()
            conf.sur_observation = ecrire
            ok = True
            try:
                for o in parcourir_fn(c["points_entree"], depot, conf):
                    pass                        # déjà écrit au fil de l'eau par le rappel
            except Exception as e:          # une collectivité en panne ne doit jamais arrêter les autres
                ok = False
                erreurs.append({"collectivite": c["id"], "etape": "parcours", "erreur": f"{type(e).__name__} {e}"[:300]})
                print(f"ERREUR {c['id']} parcours : {type(e).__name__} {e}", flush=True)
            for base in c.get("wp_media", []):
                try:
                    for o in decouvrir_wp_media(base, c.get("wp_termes", ["conseil"]), depot, Navigateur(conf),
                                                duree_max=duree_max, pages_max=c.get("wp_pages", 3),
                                                filtre=c.get("wp_filtre", "")):
                        ecrire(o)
                except Exception as e:
                    ok = False
                    erreurs.append({"collectivite": c["id"], "etape": "api_media", "erreur": f"{type(e).__name__} {e}"[:300]})
                    print(f"ERREUR {c['id']} api média : {type(e).__name__} {e}", flush=True)
            if ok and not (coupe_par_echeance and fin_avant and time.time() >= fin_avant - 5):
                terminees.add(c["id"])
            if apres_collectivite:
                apres_collectivite(c["id"], ok)
    return n


ETAT_PAR_DEFAUT = {"passage_en_cours": None, "dernier_passage_complet": None, "derniere_observation": None,
                   "derniere_execution": None, "derniere_erreur": None, "erreurs": [], "tentatives": {}, "executions": 0}


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def lire_etat(chemin: str) -> dict:
    """État persistant du robot (versionné dans git). Fichier absent ou illisible : état vide, jamais d'arrêt."""
    try:
        with open(chemin, encoding="utf-8") as f:
            e = json.load(f)
        return {**ETAT_PAR_DEFAUT, **e}
    except (OSError, ValueError):
        return dict(ETAT_PAR_DEFAUT)


def ecrire_etat(chemin: str, etat: dict) -> None:
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=1)
    os.replace(tmp, chemin)                 # écriture atomique : jamais d'état à moitié écrit


def decider(etat: dict, maintenant: datetime, intervalle_h: float = 20.0, abandon_h: float = 48.0) -> str:
    """'reprendre' un passage interrompu, 'nouveau' passage, ou 'rien' (dernier passage complet assez récent)."""
    p = etat.get("passage_en_cours")
    if p and not p.get("termine"):
        debut = datetime.fromisoformat(p["id"])
        if maintenant - debut < timedelta(hours=abandon_h):
            return "reprendre"              # sinon : passage abandonné (ses lignes restent dans le manifeste), on repart à neuf
    d = etat.get("dernier_passage_complet")
    if d and maintenant - datetime.fromisoformat(d) < timedelta(hours=intervalle_h):
        return "rien"
    return "nouveau"


def ids_deja_ecrits(manifeste: str, passage_id: str) -> set:
    deja = set()
    if os.path.exists(manifeste):
        with open(manifeste, encoding="utf-8") as f:
            for l in f:
                try:
                    o = json.loads(l)
                except ValueError:
                    continue                # ligne coupée par un arrêt brutal : ignorée, jamais fatale
                if o.get("passage") == passage_id:
                    deja.add((o["collectivite"], o["url"], o.get("sha256"), o["statut"]))
    return deja


def cycle(cfg_json: dict, archive: str, manifeste: str, etat_chemin: str, intervalle_h=20.0, fin_avant=None, seulement=None,
          delai=2.0, duree_max=0.0, sauvegarde=None, parcourir_fn=parcourir, force=False, maintenant=None) -> str:
    """Un lancement : décide (reprendre / nouveau / rien), exécute, tient l'état à jour. Renvoie la décision."""
    maintenant = maintenant or _maintenant()
    etat = lire_etat(etat_chemin)
    d = "nouveau" if (force and decider(etat, maintenant, intervalle_h) == "rien") else decider(etat, maintenant, intervalle_h)
    if d == "rien":
        print("Rien à faire : dernier passage complet récent.", flush=True)
        return d
    if d == "nouveau":
        etat["passage_en_cours"] = {"id": maintenant.isoformat(), "termine": False, "collectivites_terminees": []}
        etat["tentatives"] = {}
    p = etat["passage_en_cours"]
    etat["derniere_execution"] = maintenant.isoformat()
    etat["executions"] = etat.get("executions", 0) + 1
    terminees = set(p["collectivites_terminees"])
    deja = ids_deja_ecrits(manifeste, p["id"])
    erreurs: list = []
    dernier_flush = [time.time()]

    def enregistrer(sauver=True):
        p["collectivites_terminees"] = sorted(terminees)
        etat["erreurs"] = (etat.get("erreurs", []) + [{**e, "quand": _maintenant().isoformat()} for e in erreurs])[-30:]
        erreurs.clear()
        if etat["erreurs"]:
            etat["derniere_erreur"] = etat["erreurs"][-1]["quand"]
        ecrire_etat(etat_chemin, etat)
        if sauver and sauvegarde:
            try:
                sauvegarde()
            except Exception as e:          # la sauvegarde est best-effort : le travail continue
                print(f"ALERTE sauvegarde : {type(e).__name__} {e}", flush=True)

    def apres_observation():
        etat["derniere_observation"] = _maintenant().isoformat()
        if time.time() - dernier_flush[0] > 600:        # point de reprise toutes les 10 min
            dernier_flush[0] = time.time()
            enregistrer()

    def apres_collectivite(cid, ok):
        t = etat["tentatives"]
        t[cid] = t.get(cid, 0) + 1
        if not ok and t[cid] >= 3:
            terminees.add(cid)              # 3 pannes dans le même passage : on la laisse (signalée) pour ne pas boucler
            erreurs.append({"collectivite": cid, "etape": "abandon", "erreur": "3 pannes dans ce passage"})
        enregistrer()

    try:
        passage(cfg_json, archive, manifeste, seulement, delai, parcourir_fn, duree_max, passage_id=p["id"], deja=deja,
                terminees=terminees, fin_avant=fin_avant, apres_collectivite=apres_collectivite,
                apres_observation=apres_observation, erreurs=erreurs)
    except BaseException as e:               # y compris SystemExit/KeyboardInterrupt : l'état est écrit avant de repartir
        erreurs.append({"collectivite": "*", "etape": "cycle", "erreur": f"{type(e).__name__} {e}"[:300]})
        enregistrer()
        raise
    attendues = {c["id"] for c in cfg_json["collectivites"] if not seulement or c["id"] == seulement}
    if attendues <= terminees and not seulement:
        p["termine"] = True
        etat["dernier_passage_complet"] = _maintenant().isoformat()
        etat["derniere_reussite_id"] = p["id"]
    enregistrer()
    return d


def sauvegarde_git(script="scripts/sauvegarde.sh"):
    if os.environ.get("CI") and os.path.exists(script):
        subprocess.run(["bash", script], check=False, timeout=300)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/collectivites.json")
    ap.add_argument("--archive", default="archive")
    ap.add_argument("--manifeste", default="manifeste.jsonl")
    ap.add_argument("--seulement")
    ap.add_argument("--delai", type=float, default=2.0)
    ap.add_argument("--duree-max", type=float, default=0.0, help="secondes par collectivité")
    ap.add_argument("--etat", default="etat/statut.json")
    ap.add_argument("--cycle", action="store_true", help="mode autonome : reprend un passage interrompu, ou en démarre un si le dernier est assez ancien")
    ap.add_argument("--intervalle-heures", type=float, default=20.0)
    ap.add_argument("--fin-avant-minutes", type=float, default=0.0, help="s'arrête proprement avant cette durée (limite du job)")
    ap.add_argument("--force", action="store_true", help="avec --cycle : démarre un passage même si le dernier est récent")
    a = ap.parse_args()
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    if a.cycle:
        fin = time.time() + a.fin_avant_minutes * 60 if a.fin_avant_minutes else None
        d = cycle(cfg, a.archive, a.manifeste, a.etat, a.intervalle_heures, fin, a.seulement, a.delai, a.duree_max,
                  sauvegarde=sauvegarde_git, force=a.force)
        sortie = os.environ.get("GITHUB_OUTPUT")
        if sortie:
            with open(sortie, "a") as f:
                f.write(f"decision={d}\n")
    else:
        print(passage(cfg, a.archive, a.manifeste, a.seulement, a.delai, duree_max=a.duree_max), "observations")
