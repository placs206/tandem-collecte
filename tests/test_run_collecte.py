import json, os, tempfile, pytest
from collecte import Observation
import run_collecte as rc

def faux(points, depot, conf):
    res = [Observation(points[0], "", "present", sha256="ab"*32, mime="text/html", taille=3),
            Observation(points[0] + "x.pdf", points[0], "non_constatable", raison="bloque_403", est_document=True)]
    for o in res:
        if conf.sur_observation:
            conf.sur_observation(o)
    return res

def test_contact_obligatoire():
    with pytest.raises(SystemExit):
        rc.passage({"contact_robot": "A RENSEIGNER", "collectivites": []}, "a", "m")

def test_premiere_capture_conservee():
    d = tempfile.mkdtemp(); m = os.path.join(d, "m.jsonl")
    cfg = {"contact_robot": "x@y.fr", "collectivites": [{"id": "t", "points_entree": ["https://e.fr/"]}]}
    rc.passage(cfg, d, m, parcourir_fn=faux); rc.passage(cfg, d, m, parcourir_fn=faux)
    l = [json.loads(x) for x in open(m)]
    assert len(l) == 4 and l[0]["premiere_capture"] == l[2]["premiere_capture"]
    assert l[1]["sha256"] is None and l[1]["premiere_capture"] is None
