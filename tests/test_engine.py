import os, random, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
import engine as e
from engine import OUI, NON, NA, AV, Collectivite, Seance

CAT = e.charger_catalogue()
FIN = date(2026, 10, 22)
DEBUT = date(2024, 10, 22)


def dates(n=9):
    """n séances réparties sur la fenêtre, au moins une par trimestre complet."""
    d = date(2024, 11, 15)
    out = []
    for _ in range(n):
        out.append(d)
        d += timedelta(days=75)
    return [x for x in out if x <= FIN]


def coll(type="commune", pop=44194, extra_faits=()):
    c = Collectivite(type=type, population=pop)
    c.competences = {"dechets"}
    c.faits = set(extra_faits)
    return c


def seances_completes(c, ds, tous_oui=True, docs=("PV", "DELIB", "LISTE")):
    out = []
    for d in ds:
        s = Seance(date=d, docs=set(docs))
        for o in CAT.values():
            if o.statut == "calcule" and o.occurrence in e.PAR_SEANCE and e.applicable(o, c):
                s.resultats[o.id] = OUI if tous_oui else NON
        out.append(s)
    return out


def constats_complets(c, valeur=OUI):
    k = {}
    for o in CAT.values():
        if o.statut == "calcule" and e.applicable(o, c) and o.occurrence not in e.PAR_SEANCE and o.occurrence != "par trimestre":
            if o.condition == "aucune":
                for an in ("2025", "2026"):
                    k[(o.id, an)] = valeur
            else:
                c.faits.add(o.id)
                k[(o.id, "x")] = valeur
    return k


def test_catalogue_integrite():
    ids = [o.id for o in CAT.values()]
    assert len(ids) == len(set(ids))
    calc = [o for o in CAT.values() if o.statut == "calcule"]
    assert len(calc) == 62                      # 36 publication (dont ACT-001-T, DN-57) + 26 fonctionnement du conseil
    assert sum(o.axe.startswith("A2") for o in calc if o.id.startswith(("CS-", "PV-", "VS-"))) == 26
    assert all(o.axe for o in calc)             # un axe par obligation calculée (P06)


def test_commune_parfaite_100():
    c = coll()
    k = constats_complets(c)
    n = e.calculer(c, seances_completes(c, dates()), DEBUT, FIN, k, CAT)
    assert n.non == 0 and n.globale == 100.0


def test_rien_publie_est_zero_sur_les_seances():
    c = coll()
    n = e.calculer(c, [], DEBUT, FIN, {}, CAT)
    # séances attendues générées : les obligations PV/délibérations comptent « non » (P56)
    assert n.oui == 0 and n.non > 0
    assert n.globale == 0.0


def test_garde_fou_p36_rien_publie_ne_bat_pas_publie_avec_defauts():
    c = coll()
    k = constats_complets(c, valeur=NON)
    vide = e.calculer(c, [], DEBUT, FIN, {}, CAT)
    avec_defauts = e.calculer(c, seances_completes(c, dates(), tous_oui=False), DEBUT, FIN, k, CAT)
    # publier avec des défauts : les obligations d'existence (E) restent « non » seulement si le doc manque ;
    # ici les documents existent, mais toutes les mentions sont fausses -> aucun avantage, jamais pire que rien publier
    assert avec_defauts.globale >= vide.globale or avec_defauts.globale is None


def test_p36_monotonie_aleatoire():
    """Transformer un « non » en « oui » ne baisse jamais la note ; publier un document absent ne la baisse pas."""
    rnd = random.Random(7)
    c = coll()
    ds = dates()
    for _ in range(50):
        docs_par_seance = [set(x for x in ("PV", "DELIB", "LISTE") if rnd.random() < 0.6) for _ in ds]
        base = []
        for d, docs in zip(ds, docs_par_seance):
            s = Seance(date=d, docs=set(docs))
            for o in CAT.values():
                if o.statut == "calcule" and o.occurrence in e.PAR_SEANCE and e.applicable(o, c):
                    s.resultats[o.id] = rnd.choice([OUI, NON])
            base.append(s)
        n0 = e.calculer(c, base, DEBUT, FIN, {}, CAT)
        # on ajoute un document absent avec toutes les mentions fausses : jamais pire
        i = rnd.randrange(len(base))
        manque = [x for x in ("PV", "DELIB", "LISTE") if x not in base[i].docs]
        if not manque:
            continue
        import copy
        v2 = copy.deepcopy(base)
        v2[i].docs.add(manque[0])
        for o in CAT.values():
            if o.document == manque[0] and o.occurrence in e.PAR_SEANCE:
                # mentions fausses ; le « maintien » (-M) reste « oui » : le document n'a pas disparu (P54)
                # existence (-E) : « oui » puisqu'il est publié (DN-62 : sinon le délai -D ne serait pas compté)
                v2[i].resultats[o.id] = OUI if o.id.endswith(("-M", "-E")) else NON
        n1 = e.calculer(c, v2, DEBUT, FIN, {}, CAT)
        assert (n1.globale or 0) >= (n0.globale or 0) - 1e-9


def test_p55_dernier_pv_non_compte():
    c = coll()
    ds = dates()
    sc = seances_completes(c, ds)
    n = e.calculer(c, sc, DEBUT, FIN, {}, CAT)
    nb_pv = len([l for l in n.lignes if l.obligation == "PV-01"])
    assert nb_pv == len(sc) - 1                  # la dernière séance n'arrête pas encore son PV


def test_conditionnel_non_compte_sans_fait():
    c = coll()
    n = e.calculer(c, seances_completes(c, dates()), DEBUT, FIN, {}, CAT)
    assert not [l for l in n.lignes if l.obligation == "URB-001-E"]      # PLU : fait non établi (P53)
    c.faits.add("URB-001-E")
    n2 = e.calculer(c, seances_completes(c, dates()), DEBUT, FIN, {("URB-001-E", "x"): OUI}, CAT)
    assert [l for l in n2.lignes if l.obligation == "URB-001-E" and l.resultat == OUI]


def test_a_verifier_non_compte_et_baisse_couverture():
    c = coll()
    sc = seances_completes(c, dates())
    sc[0].resultats["PV-05"] = AV
    n = e.calculer(c, sc, DEBUT, FIN, constats_complets(c), CAT)
    assert n.a_verifier >= 1 and n.couverture < 100 and n.globale == 100.0


def test_modules_population():
    petit = coll(pop=800)
    salon = coll(pop=44194)
    for oid, attendu_petit, attendu_salon in [("RH-010-E", False, True), ("CS-02", False, True),
                                               ("FIN-007-E", False, True), ("URB-021-E", False, True),
                                               ("ENV-003-E", False, False), ("OUV-005-E", False, True),
                                               ("ACT-002-E", True, True)]:
        assert e.applicable(CAT[oid], petit) == attendu_petit, oid
        assert e.applicable(CAT[oid], salon) == attendu_salon, oid


def test_epci_traite_comme_commune_de_1000():
    petite_cc = coll(type="communaute_communes", pop=600)
    assert e.applicable(CAT["CS-02"], petite_cc)          # CGCT L5211-1
    assert e.applicable(CAT["CS-05"], petite_cc)
    assert not e.applicable(CAT["URB-021-E"], petite_cc)  # L2241-1 : communes seulement
    assert not e.applicable(CAT["ENV-002-E"], petite_cc)  # PCAET : plus de 20 000


def test_competence_transferee_p27():
    commune = coll(); commune.competences = set()
    metropole = coll(type="metropole", pop=1_900_000); metropole.competences = {"dechets"}
    assert not e.applicable(CAT["SPL-003-E"], commune)
    assert e.applicable(CAT["SPL-003-E"], metropole)


def test_trimestre_sans_document_donne_seance_attendue():
    c = coll()
    sc = seances_completes(c, [date(2025, 2, 10), date(2025, 3, 20)])   # un seul trimestre couvert
    n = e.calculer(c, sc, DEBUT, FIN, {}, CAT)
    attendues = {l.occurrence for l in n.lignes if l.occurrence.endswith("*")}
    assert len(attendues) >= 5
    cs01 = [l for l in n.lignes if l.obligation == "CS-01"]
    assert sum(l.resultat == NON for l in cs01) >= 5   # une séance par trimestre exigée (L2121-7)


def test_maintien_document_absent_non():
    c = coll()
    n = e.calculer(c, [], DEBUT, FIN, {}, CAT)
    m = [l for l in n.lignes if l.obligation == "ACT-001-M"]
    assert m and all(l.resultat == NON for l in m)    # DN-07 (arbitrage 23/10/2026) : document absent = « non »


def test_fenetre_24_mois():
    c = coll()
    anciennes = [Seance(date=date(2022, 1, 5), docs={"PV", "DELIB", "LISTE"})]
    n = e.calculer(c, anciennes, DEBUT, FIN, {}, CAT)
    assert not [l for l in n.lignes if l.occurrence.startswith("2022")]


def test_publier_puis_retirer_ne_coute_pas_plus_que_ne_jamais_publier():
    """DN-07 (arbitrage 23/10/2026) : le maintien est « non » dans les deux cas ; publier puis retirer
    ne coûte donc pas plus cher que ne jamais publier (effet pervers écarté)."""
    c = coll()
    ds = dates()
    jamais = [Seance(date=d, docs=set()) for d in ds]
    retire = []
    for d in ds:
        s = Seance(date=d, docs={"DELIB"})
        s.resultats["ACT-001-M"] = NON
        s.resultats["ACT-001-E"] = OUI
        retire.append(s)
    nj = e.calculer(c, jamais, DEBUT, FIN, {}, CAT)
    nr = e.calculer(c, retire, DEBUT, FIN, {}, CAT)
    m_jamais = [l for l in nj.lignes if l.obligation == "ACT-001-M"]
    m_retire = [l for l in nr.lignes if l.obligation == "ACT-001-M"]
    assert all(l.resultat == NON for l in m_jamais)
    assert all(l.resultat == NON for l in m_retire)
    assert nr.globale >= nj.globale
    # l'existence (ACT-001-E) reste, elle, strictement meilleure pour le document publié
    assert sum(l.resultat == OUI for l in nr.lignes if l.obligation == "ACT-001-E") > 0


def test_delai_non_compte_si_document_absent_dn62():
    s = Seance(date=date(2026, 3, 12), docs=set())
    s2 = Seance(date=date(2026, 4, 9), docs={"PV"}, resultats={"ACT-002-E": OUI, "ACT-002-D": OUI})
    n = e.calculer(e.Collectivite(type="commune", population=5000), [s, s2], date(2026, 1, 1), date(2026, 6, 30))
    d = [l for l in n.lignes if l.obligation == "ACT-002-D"]
    ex = [l for l in n.lignes if l.obligation == "ACT-002-E"]
    assert all(l.occurrence != "2026-03-12" for l in d)          # PV absent : pas de ligne de délai
    assert any(l.occurrence == "2026-03-12" and l.resultat == NON for l in ex)   # un seul « non », sur l'existence
