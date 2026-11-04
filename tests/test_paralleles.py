"""Collectivités traitées en même temps quand elles n'ont aucun site en commun (réduction des minutes GitHub)."""
import os, tempfile, threading, time
from datetime import datetime, timezone
from collecte import Observation
import run_collecte as rc

T0 = datetime(2026, 11, 5, 13, 0, tzinfo=timezone.utc)


def c(id_, *urls, autres=()):
    return {"id": id_, "points_entree": list(urls), "hotes_autorises": list(autres)}


def test_regroupement_par_site():
    a = c("a", "https://www.a.fr/"); b = c("b", "https://b.fr/x", autres=["portail.fr"])
    m = c("m", "https://portail.fr/"); z = c("z", "https://z.fr/")
    files = rc.files_paralleles([a, b, m, z])
    assert sorted([x["id"] for x in f] for f in files) == [["a"], ["b", "m"], ["z"]]   # b et m partagent portail.fr
    assert rc.files_paralleles([c("x", "https://a.fr/"), c("y", "https://www.a.fr/p")]) == [[c("x", "https://a.fr/"), c("y", "https://www.a.fr/p")]]


def lent(debuts, fins):
    def f(points, depot, conf):
        cid = points[0]
        debuts[cid] = time.time()
        for i in range(20):
            conf.sur_observation(Observation(f"{cid}doc{i}.pdf", cid, "present", sha256=f"{abs(hash(cid))%10}{i:063d}", est_document=True))
            time.sleep(0.01)
        fins[cid] = time.time()
        return []
    return f


def test_sites_differents_traites_en_meme_temps_sans_perte_ni_doublon():
    cfg = {"contact_robot": "x@y.fr", "collectivites": [c("a", "https://a.fr/"), c("b", "https://b.fr/")]}
    d = tempfile.mkdtemp(); m = os.path.join(d, "manifeste"); e = os.path.join(d, "etat", "statut.json")
    debuts, fins = {}, {}
    sauvegardes = []
    rc.cycle(cfg, d, m, e, parcourir_fn=lent(debuts, fins), sauvegarde=lambda: sauvegardes.append(1), maintenant=T0)
    assert debuts["https://b.fr/"] < fins["https://a.fr/"] and debuts["https://a.fr/"] < fins["https://b.fr/"]   # chevauchement
    lignes = list(rc.lire_manifeste(m))
    assert len(lignes) == 40 and len({(o["collectivite"], o["url"]) for o in lignes}) == 40
    etat = rc.lire_etat(e)
    assert etat["passage_en_cours"]["termine"] and etat["passage_en_cours"]["collectivites_terminees"] == ["a", "b"]
    assert len(sauvegardes) >= 2


def test_meme_site_jamais_en_meme_temps():
    cfg = {"contact_robot": "x@y.fr", "collectivites": [c("a", "https://a.fr/1"), c("b", "https://a.fr/2")]}
    d = tempfile.mkdtemp(); m = os.path.join(d, "manifeste"); e = os.path.join(d, "etat", "statut.json")
    debuts, fins = {}, {}
    rc.cycle(cfg, d, m, e, parcourir_fn=lent(debuts, fins), maintenant=T0)
    assert fins["https://a.fr/1"] <= debuts["https://a.fr/2"]


def test_panne_d_une_file_n_arrete_pas_l_autre():
    cfg = {"contact_robot": "x@y.fr", "collectivites": [c("a", "https://a.fr/"), c("b", "https://b.fr/")]}
    d = tempfile.mkdtemp(); m = os.path.join(d, "manifeste"); e = os.path.join(d, "etat", "statut.json")
    def f(points, depot, conf):
        if "a.fr" in points[0]:
            raise RuntimeError("site a en panne")
        conf.sur_observation(Observation("https://b.fr/doc.pdf", "", "present", sha256="b" * 64, est_document=True))
        return []
    rc.cycle(cfg, d, m, e, parcourir_fn=f, maintenant=T0)
    etat = rc.lire_etat(e)
    assert etat["passage_en_cours"]["collectivites_terminees"] == ["b"] and not etat["passage_en_cours"]["termine"]
    assert any(x["collectivite"] == "a" for x in etat["erreurs"])
