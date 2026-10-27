import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constats import (Fait, Piece, construire_seance, delai_pv,  # noqa: E402
                      deliberations_completes, maintien, resultat_faits)
from engine import AV, NA, NON, OUI, Collectivite, calculer  # noqa: E402

TOUS_FAITS_PV = ["seance_date", "heure", "president", "presents", "secretaire", "quorum",
                 "ordre_du_jour", "deliberations_adoptees", "rapports_cites",
                 "resultat_scrutins", "teneur_discussions", "signature_ou_mention_signe",
                 "quorum_atteint"]


def pv_complet(**remplace):
    faits = {k: Fait(k, True) for k in TOUS_FAITS_PV}
    faits["scrutin_particulier_demande"] = Fait("scrutin_particulier_demande", "aucune_demande")
    for k, v in remplace.items():
        faits[k] = v
    return Piece("PV", faits=faits)


def test_resultat_faits_regles_de_base():
    assert resultat_faits({"a": Fait("a", True)}, ["a"]) == OUI
    assert resultat_faits({"a": Fait("a", False)}, ["a"]) == NON
    assert resultat_faits({}, ["a"]) == AV
    assert resultat_faits({"a": Fait("a", True, douteux=True)}, ["a"]) == AV
    # un faux établi l'emporte sur un doute
    assert resultat_faits({"a": Fait("a", False), "b": Fait("b", None)}, ["a", "b"]) == NON


def test_decision_humaine_prime():
    f = Fait("a", False, douteux=True, tranche=True)
    assert resultat_faits({"a": f}, ["a"]) == OUI


def test_aucune_demande_de_scrutin_est_non_applicable():
    s = construire_seance(date(2026, 3, 12), [pv_complet()])
    assert s.resultats["PV-09"] == NA


def test_seance_avec_pv_complet():
    s = construire_seance(date(2026, 3, 12), [pv_complet(), Piece("EXTRAIT_REGISTRE", faits={
        "signature": Fait("signature", True), "numero_deliberation": Fait("numero_deliberation", True)}),
        Piece("LISTE_DELIB")])
    assert s.docs == {"PV", "DELIB", "LISTE"}
    assert s.resultats["PV-12"] == OUI and s.resultats["VS-07"] == OUI
    assert s.resultats["ACT-002-E"] == OUI and s.resultats["ACT-003-E"] == OUI


def test_extrait_ne_vaut_pas_pv_dn13():
    s = construire_seance(date(2026, 3, 12), [Piece("EXTRAIT_REGISTRE")])
    assert "PV" not in s.docs and "DELIB" in s.docs
    # le moteur compte « non » pour toutes les obligations PV-xx de cette séance quand une séance suit
    c = Collectivite("commune", 44194)
    suivante = construire_seance(date(2026, 4, 9), [Piece("EXTRAIT_REGISTRE")])
    note = calculer(c, [s, suivante], date(2026, 1, 1), date(2026, 6, 30))
    pv = [l for l in note.lignes if l.obligation == "PV-12" and l.occurrence.startswith("2026-03-12")]
    assert pv and pv[0].resultat == NON


def test_type_douteux_donne_a_verifier_et_non_non():
    s = construire_seance(date(2026, 3, 12), [Piece("PV", douteux_type=True)])
    assert s.resultats["PV-01"] == AV and s.resultats["ACT-002-E"] == AV


def test_fait_manquant_dans_pv_donne_non():
    s = construire_seance(date(2026, 3, 12), [pv_complet(signature_ou_mention_signe=Fait("x", False))])
    assert s.resultats["PV-12"] == NON


def test_delai_pv():
    s1 = construire_seance(date(2026, 3, 12), [pv_complet()])
    s2 = construire_seance(date(2026, 4, 9), [pv_complet()])
    s3 = construire_seance(date(2026, 5, 7), [pv_complet()])
    delai_pv([s1, s2, s3], {date(2026, 3, 12): date(2026, 4, 14),   # 5 jours après N+1 : oui
                            date(2026, 4, 9): date(2026, 5, 20),    # 13 jours après N+1 : non
                            date(2026, 5, 7): None})
    assert s1.resultats["ACT-002-D"] == OUI
    assert s2.resultats["ACT-002-D"] == NON
    assert "ACT-002-D" not in s3.resultats   # dernière séance : pas jugée (P55)


def test_delai_pv_date_inconnue():
    s1 = construire_seance(date(2026, 3, 12), [pv_complet()])
    s2 = construire_seance(date(2026, 4, 9), [pv_complet()])
    delai_pv([s1, s2], {date(2026, 3, 12): None})
    assert s1.resultats["ACT-002-D"] == AV


def test_deliberations_completes_p60():
    assert deliberations_completes({1, 2, 3}, {1, 2, 3, 4}) == OUI
    assert deliberations_completes({1, 2, 3}, {1, 3}) == NON
    assert deliberations_completes(None, {1}) == AV


def test_maintien_p54():
    pub = date(2026, 3, 15)
    assert maintien(pub, [(date(2026, 4, 1), False)]) == NON                        # jamais observé (DN-07 : non)
    assert maintien(pub, [(date(2026, 3, 20), True), (date(2026, 4, 10), False)]) == NON
    assert maintien(pub, [(date(2026, 3, 20), True), (date(2026, 5, 20), True)]) == OUI
    assert maintien(pub, [(date(2026, 3, 20), True), (date(2026, 4, 3), True)]) == AV   # fenêtre trop courte
    # disparition après 2 mois : permise
    assert maintien(pub, [(date(2026, 3, 20), True), (date(2026, 5, 20), True), (date(2026, 7, 1), False)]) == OUI


def test_note_de_bout_en_bout_pv_parfaits_sans_dependre_du_reste():
    """Séances parfaites : les lignes calculées par séance sont toutes « oui » ou « non applicable »."""
    c = Collectivite("commune", 44194)
    seances = [construire_seance(date(2026, m, 12), [
        pv_complet(),
        Piece("EXTRAIT_REGISTRE", faits={"signature": Fait("s", True), "numero_deliberation": Fait("n", True)}),
        Piece("LISTE_DELIB")]) for m in (1, 2, 3, 4, 5, 6)]
    note = calculer(c, seances, date(2026, 1, 1), date(2026, 6, 30))
    pv_lignes = [l for l in note.lignes if l.obligation.startswith("PV-") and not l.occurrence.endswith("*")]
    assert pv_lignes and all(l.resultat in (OUI, NA) for l in pv_lignes)


def test_aucune_certaines_toutes_dn57():
    from constats import aucune_certaines_toutes
    assert aucune_certaines_toutes({1, 2, 3}, set()) == (NON, NON)
    assert aucune_certaines_toutes({1, 2, 3}, {1, 3}) == (OUI, NON)
    assert aucune_certaines_toutes({1, 2, 3}, {1, 2, 3}) == (OUI, OUI)
    assert aucune_certaines_toutes(None, {1}) == (OUI, AV)       # pas de liste de référence : complétude à vérifier
    assert aucune_certaines_toutes(None, set()) == (NON, AV)


def test_seance_deliberations_partielles():
    delib = Piece("DELIB", faits={})
    s = construire_seance(date(2026, 5, 5), [delib], numeros_attendus={1, 2, 3}, numeros_trouves={1, 2})
    assert (s.resultats["ACT-001-E"], s.resultats["ACT-001-T"]) == (OUI, NON)
    s = construire_seance(date(2026, 5, 5), [delib], numeros_attendus={1, 2, 3}, numeros_trouves={1, 2, 3})
    assert (s.resultats["ACT-001-E"], s.resultats["ACT-001-T"]) == (OUI, OUI)
    s = construire_seance(date(2026, 5, 5), [], numeros_attendus={1, 2, 3}, numeros_trouves=set())
    assert (s.resultats["ACT-001-E"], s.resultats["ACT-001-T"]) == (NON, NON)


def test_existence_pv_par_contenu_dn63():
    from constats import existence_pv_par_contenu, FAITS_PV
    tous = {k: OUI for k in FAITS_PV}
    assert existence_pv_par_contenu(tous) == OUI
    assert existence_pv_par_contenu({**tous, "PV-09": "non_applicable"}) == OUI
    assert existence_pv_par_contenu({**tous, "PV-11": NON}) == NON
    assert existence_pv_par_contenu({**tous, "PV-12": AV}) == AV
    assert existence_pv_par_contenu({**tous, "PV-11": NON, "PV-12": AV}) == NON
