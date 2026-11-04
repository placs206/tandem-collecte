"""Manifeste découpé (A-03) et contrôle de qualité des passages (A-04)."""
import json, os, tempfile
from datetime import datetime, timedelta, timezone
from collecte import Observation
import run_collecte as rc
import surveillance as sv
import importlib.util

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("decouper", os.path.join(ICI, "scripts", "decouper_manifeste.py"))
dec = importlib.util.module_from_spec(spec); spec.loader.exec_module(dec)

CFG = {"contact_robot": "x@y.fr", "collectivites": [{"id": "a", "points_entree": ["https://a.fr/"]}, {"id": "b", "points_entree": ["https://b.fr/"]}]}
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def chemins():
    d = tempfile.mkdtemp()
    return d, os.path.join(d, "manifeste"), os.path.join(d, "etat", "statut.json")


def fabrique(n_par_coll):
    """Faux parcours : n_par_coll[id] documents présents pour chaque collectivité."""
    def f(points, depot, conf):
        cid = "a" if "a.fr" in points[0] else "b"
        for i in range(n_par_coll[cid]):
            conf.sur_observation(Observation(f"{points[0]}doc{i}.pdf", points[0], "present", sha256=f"{cid}{i:062d}", est_document=True))
        return []
    return f


def test_un_fichier_par_collectivite_et_par_passage_reprise_sans_doublon():
    d, m, e = chemins()
    rc.cycle(CFG, d, m, e, parcourir_fn=fabrique({"a": 3, "b": 2}), maintenant=T0)
    fichiers = sorted(os.path.relpath(f, m) for f in rc.fichiers_manifeste(m))
    assert fichiers == [os.path.join("a", T0.isoformat().replace(":", "-") + ".jsonl"),
                        os.path.join("b", T0.isoformat().replace(":", "-") + ".jsonl")]
    # même passage repris : aucune ligne écrite deux fois
    etat = rc.lire_etat(e); etat["passage_en_cours"]["termine"] = False; etat["passage_en_cours"]["collectivites_terminees"] = []
    rc.ecrire_etat(e, etat)
    rc.cycle(CFG, d, m, e, parcourir_fn=fabrique({"a": 3, "b": 2}), maintenant=T0 + timedelta(hours=1))
    assert len(list(rc.lire_manifeste(m))) == 5


def test_premiere_capture_lue_dans_l_ancien_fichier_pendant_la_transition():
    d, m, e = chemins()
    ancien = m + ".jsonl"
    open(ancien, "w").write(json.dumps({"collectivite": "a", "passage": "2026-10-01T00:00:00+00:00", "url": "https://a.fr/doc0.pdf",
                                        "statut": "present", "sha256": "a" + "0" * 62, "premiere_capture": "2026-10-01T00:00:00+00:00"}) + "\n")
    rc.cycle(CFG, d, m, e, parcourir_fn=fabrique({"a": 1, "b": 0}), maintenant=T0)
    nouvelles = [o for o in rc.lire_manifeste(m) if o["passage"] == T0.isoformat()]
    assert nouvelles[0]["premiere_capture"] == "2026-10-01T00:00:00+00:00"


def test_decoupage_sans_perte_puis_sans_effet():
    d = tempfile.mkdtemp(); src = os.path.join(d, "manifeste.jsonl"); dos = os.path.join(d, "manifeste")
    lignes = [json.dumps({"collectivite": c, "passage": p, "url": f"u{i}", "statut": "present"}, ensure_ascii=False)
              for i, (c, p) in enumerate([("a", "P1"), ("b", "P1"), ("a", "P2"), ("a", "P1")])] + ['{"coupée']
    open(src, "w", encoding="utf-8").write("\n".join(lignes) + "\n")
    assert dec.decouper(src, dos) == 5 and not os.path.exists(src)
    relu = []
    for f in rc.fichiers_manifeste(dos):
        relu += open(f, encoding="utf-8").read().splitlines()
    assert sorted(relu) == sorted(lignes)                                   # octet pour octet, rien perdu
    assert open(os.path.join(dos, "a", "P1.jsonl")).read().splitlines() == [lignes[0], lignes[3]]   # ordre conservé
    assert dec.decouper(src, dos) == 0                                      # déjà fait : sans effet


def test_decoupage_refuse_d_ecraser():
    d = tempfile.mkdtemp(); src = os.path.join(d, "manifeste.jsonl"); dos = os.path.join(d, "manifeste")
    open(src, "w").write(json.dumps({"collectivite": "a", "passage": "P1", "url": "u", "statut": "present"}) + "\n")
    os.makedirs(os.path.join(dos, "a")); open(os.path.join(dos, "a", "P1.jsonl"), "w").write("x\n")
    try:
        dec.decouper(src, dos); assert False
    except SystemExit:
        pass
    assert os.path.exists(src) and open(os.path.join(dos, "a", "P1.jsonl")).read() == "x\n"


def test_passage_incomplet_signale():
    d, m, e = chemins()
    for i in range(3):                                   # trois passages normaux
        rc.cycle(CFG, d, m, e, parcourir_fn=fabrique({"a": 100, "b": 50}), maintenant=T0 + timedelta(days=i), force=True)
    assert rc.lire_etat(e)["qualite"]["degradees"] == []
    rc.cycle(CFG, d, m, e, parcourir_fn=fabrique({"a": 7, "b": 50}), maintenant=T0 + timedelta(days=3), force=True)   # comme le 31/10
    etat = rc.lire_etat(e)
    assert etat["passage_en_cours"]["termine"] and etat["qualite"]["degradees"] == ["a"]
    assert etat["qualite"]["collectivites"]["a"] == {"observees": 7, "reference": 100}
    anomalies, relancer = sv.diagnostiquer(etat, T0 + timedelta(days=3, hours=1))
    assert any("incomplet" in x and "a (7 adresses" in x for x in anomalies) and not relancer
    rc.cycle(CFG, d, m, e, parcourir_fn=fabrique({"a": 100, "b": 50}), maintenant=T0 + timedelta(days=4), force=True)   # retour à la normale
    assert rc.lire_etat(e)["qualite"]["degradees"] == []
    assert sv.diagnostiquer(rc.lire_etat(e), T0 + timedelta(days=4, hours=1))[0] == []


def test_collectivite_sans_aucune_observation_signalee_meme_sans_historique():
    d, m, e = chemins()
    rc.cycle(CFG, d, m, e, parcourir_fn=fabrique({"a": 5, "b": 0}), maintenant=T0)
    assert rc.lire_etat(e)["qualite"]["degradees"] == ["b"]
