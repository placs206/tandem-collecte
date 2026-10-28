import json, os, tempfile, time
from datetime import datetime, timedelta, timezone
import pytest
from collecte import Observation
import run_collecte as rc
import surveillance as sv

CFG = {"contact_robot": "x@y.fr", "collectivites": [{"id": "a", "points_entree": ["https://a.fr/"]}, {"id": "b", "points_entree": ["https://b.fr/"]}]}
T0 = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def faux(points, depot, conf):
    res = [Observation(points[0], "", "present", sha256="ab" * 32, mime="text/html", taille=3)]
    for o in res:
        conf.sur_observation(o)
    return res


def chemins():
    d = tempfile.mkdtemp()
    return d, os.path.join(d, "m.jsonl"), os.path.join(d, "etat", "statut.json")


def lignes(m):
    return [json.loads(x) for x in open(m)]


def test_decider():
    vide = dict(rc.ETAT_PAR_DEFAUT)
    assert rc.decider(vide, T0) == "nouveau"
    recent = {**vide, "dernier_passage_complet": (T0 - timedelta(hours=3)).isoformat()}
    assert rc.decider(recent, T0) == "rien"
    ancien = {**vide, "dernier_passage_complet": (T0 - timedelta(hours=21)).isoformat()}
    assert rc.decider(ancien, T0) == "nouveau"
    coupe = {**ancien, "passage_en_cours": {"id": (T0 - timedelta(hours=5)).isoformat(), "termine": False}}
    assert rc.decider(coupe, T0) == "reprendre"
    abandonne = {**ancien, "passage_en_cours": {"id": (T0 - timedelta(hours=50)).isoformat(), "termine": False}}
    assert rc.decider(abandonne, T0) == "nouveau"


def test_cycle_complet_puis_rien():
    d, m, e = chemins()
    assert rc.cycle(CFG, d, m, e, parcourir_fn=faux, maintenant=T0) == "nouveau"
    etat = rc.lire_etat(e)
    assert etat["passage_en_cours"]["termine"] and etat["dernier_passage_complet"]
    n = len(lignes(m))
    assert rc.cycle(CFG, d, m, e, parcourir_fn=faux, maintenant=datetime.now(timezone.utc)) == "rien"
    assert len(lignes(m)) == n                     # aucun doublon, aucune requête


def test_reprise_apres_interruption_sans_doublon():
    d, m, e = chemins()
    appels = []

    def plante_sur_b(points, depot, conf):
        appels.append(points[0])
        if "b.fr" in points[0] and len(appels) < 3:
            conf.sur_observation(Observation(points[0], "", "present", sha256="cd" * 32, mime="text/html", taille=1))
            raise KeyboardInterrupt("coupure du job")
        return faux(points, depot, conf)
    with pytest.raises(KeyboardInterrupt):
        rc.cycle(CFG, d, m, e, parcourir_fn=plante_sur_b, maintenant=T0)
    etat = rc.lire_etat(e)
    assert etat["passage_en_cours"]["collectivites_terminees"] == ["a"] and not etat["passage_en_cours"]["termine"]
    avant = len(lignes(m))
    # le lancement suivant reprend le MÊME passage, ne refait pas « a », et ne réécrit pas la ligne déjà écrite de « b »
    assert rc.cycle(CFG, d, m, e, parcourir_fn=plante_sur_b, maintenant=T0 + timedelta(hours=6)) == "reprendre"
    L = lignes(m)
    assert {x["passage"] for x in L} == {etat["passage_en_cours"]["id"]}
    assert appels.count("https://a.fr/") == 1
    cles = [(x["collectivite"], x["url"], x["sha256"], x["statut"]) for x in L]
    assert len(cles) == len(set(cles)) and len(L) >= avant
    assert rc.lire_etat(e)["passage_en_cours"]["termine"]


def test_panne_isolee_trois_fois_puis_abandon_signale():
    d, m, e = chemins()

    def casse_a(points, depot, conf):
        if "a.fr" in points[0]:
            raise RuntimeError("panne")
        return faux(points, depot, conf)
    for i in range(3):
        rc.cycle(CFG, d, m, e, parcourir_fn=casse_a, maintenant=T0 + timedelta(hours=6 * i))
    etat = rc.lire_etat(e)
    assert etat["passage_en_cours"]["termine"]               # ne boucle pas indéfiniment
    assert any(x["etape"] == "abandon" and x["collectivite"] == "a" for x in etat["erreurs"])
    assert etat["derniere_erreur"]


def test_echeance_arrete_proprement():
    d, m, e = chemins()
    rc.cycle(CFG, d, m, e, parcourir_fn=faux, fin_avant=time.time() + 5, maintenant=T0)   # < 60 s : rien démarré
    etat = rc.lire_etat(e)
    assert not etat["passage_en_cours"]["termine"] and etat["passage_en_cours"]["collectivites_terminees"] == []
    assert rc.cycle(CFG, d, m, e, parcourir_fn=faux, maintenant=T0 + timedelta(hours=1)) == "reprendre"
    assert rc.lire_etat(e)["passage_en_cours"]["termine"]


def test_etat_et_manifeste_abimes_ne_bloquent_pas():
    d, m, e = chemins()
    os.makedirs(os.path.dirname(e)); open(e, "w").write("{pas du json")
    open(m, "w").write('{"collectivite": "a", "passage": "x"\n')       # ligne coupée par un arrêt brutal
    assert rc.cycle(CFG, d, m, e, parcourir_fn=faux, maintenant=T0) == "nouveau"
    ok = 0
    for l in open(m).read().splitlines()[1:]:
        json.loads(l); ok += 1                                         # les lignes écrites ensuite sont intactes
    assert ok >= 2


def test_sauvegarde_appelee_et_sans_effet_sur_erreur():
    d, m, e = chemins()
    n = []
    def sauve():
        n.append(1); raise OSError("git indisponible")
    rc.cycle(CFG, d, m, e, parcourir_fn=faux, sauvegarde=sauve, maintenant=T0)
    assert len(n) >= 2 and rc.lire_etat(e)["passage_en_cours"]["termine"]


def test_surveillance():
    ok = {"dernier_passage_complet": (T0 - timedelta(hours=5)).isoformat(), "passage_en_cours": None}
    assert sv.diagnostiquer(ok, T0) == ([], False)
    vieux = {"dernier_passage_complet": (T0 - timedelta(hours=40)).isoformat()}
    a, r = sv.diagnostiquer(vieux, T0)
    assert a and r
    bloque = {**ok, "passage_en_cours": {"termine": False}, "derniere_observation": (T0 - timedelta(hours=14)).isoformat()}
    a, r = sv.diagnostiquer(bloque, T0)
    assert a and not r
    assert sv.diagnostiquer({}, T0)[0]
