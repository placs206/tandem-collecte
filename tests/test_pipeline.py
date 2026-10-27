import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import AV, NA, NON, OUI, Collectivite, calculer  # noqa: E402
from extraction_regles import extraire_date_seance, extraire_pv  # noqa: E402
from pipeline import PieceBrute, traiter_seance  # noqa: E402
from typage import normaliser  # noqa: E402

PV_COMPLET = """PROCÈS-VERBAL DE LA SÉANCE DU CONSEIL MUNICIPAL du 12 mars 2026
L'an deux mille vingt-six, le 12 mars à 18h30, le conseil municipal s'est réuni sous la présidence de
Madame Claire Dupont, maire. Membres présents : M. Martin, Mme Roux, M. Petit.
Secrétaire de séance : M. Martin. Le quorum étant atteint, le conseil peut valablement délibérer.
Ordre du jour : 1. Budget primitif 2. Subventions.
Aucune demande de scrutin public ou secret n'a été formulée.
Au vu du rapport de Mme Roux, adjointe aux finances, le budget est adopté. Pour : 25, contre : 3, abstentions : 1.
M. Petit prend la parole et souligne le niveau des dépenses. Mme Roux précise que les recettes augmentent.
Après discussion, la séance est levée à 21h.
Le maire, Claire Dupont (signé)"""

PV_SANS_SIGNATURE = PV_COMPLET.replace("Le maire, Claire Dupont (signé)", "Fait à Salon.")


def test_faits_passe_1_sur_pv_complet():
    f = extraire_pv(PV_COMPLET)
    for k in ("seance_date", "heure", "president", "presents", "secretaire", "quorum", "ordre_du_jour",
              "deliberations_adoptees", "rapports_cites", "resultat_scrutins", "teneur_discussions",
              "signature_ou_mention_signe"):
        assert f[k].valeur is True, k
    assert f["scrutin_particulier_demande"].valeur == "aucune_demande"


def test_regle_fixe_ne_conclut_jamais_non():
    f = extraire_pv(PV_SANS_SIGNATURE)
    assert f["signature_ou_mention_signe"].valeur is None        # non trouvé -> passe 2 ou relecture, pas « non »


def test_dates():
    assert extraire_date_seance(normaliser("séance du 1er avril 2026")) == date(2026, 4, 1)
    assert extraire_date_seance(normaliser("séance du conseil le 05/03/2026")) == date(2026, 3, 5)
    assert extraire_date_seance("rien") is None


def test_seance_complete_donne_oui():
    s, douteux = traiter_seance(date(2026, 3, 12), [PieceBrute(PV_COMPLET)])
    assert not douteux
    assert s.docs == {"PV"}
    assert s.resultats["PV-12"] == OUI and s.resultats["PV-05"] == OUI and s.resultats["PV-09"] == NA


def test_fait_non_trouve_donne_a_verifier_et_cas_douteux():
    s, douteux = traiter_seance(date(2026, 3, 12), [PieceBrute(PV_SANS_SIGNATURE)])
    assert s.resultats["PV-12"] == AV
    assert any(d["motif"].startswith("faits non trouvés") and "signature_ou_mention_signe" in d["faits"]
               for d in douteux)


def test_decision_humaine_prime_sur_le_typage_douteux():
    texte = "LISTE DES DÉLIBÉRATIONS - ORDRE DU JOUR du conseil du 12 mars 2026\n1. Budget"
    s1, d1 = traiter_seance(date(2026, 3, 12), [PieceBrute(texte)])
    assert d1 and s1.resultats.get("ACT-003-E") == AV            # type douteux : à vérifier, jamais « non »
    s2, d2 = traiter_seance(date(2026, 3, 12), [PieceBrute(texte, type_tranche="LISTE_DELIB")])
    assert not d2 and s2.resultats["ACT-003-E"] == OUI


def test_note_de_bout_en_bout_avec_pv_et_extrait():
    seances = []
    noms = {1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin"}
    for m in (1, 2, 3, 4, 5, 6):
        s, _ = traiter_seance(date(2026, m, 12), [PieceBrute(PV_COMPLET.replace("12 mars", f"12 {noms[m]}"))])
        seances.append(s)
    note = calculer(Collectivite("commune", 44194), seances, date(2026, 1, 1), date(2026, 6, 30))
    pv = [l for l in note.lignes if l.obligation.startswith("PV-") and not l.occurrence.endswith("*")]
    assert pv and all(l.resultat in (OUI, NA) for l in pv)
    assert note.globale is not None and 0 <= note.globale <= 100


def test_extrait_du_registre_seul_donne_non_sur_les_pv():
    texte = ("EXTRAIT DU REGISTRE DES DÉLIBÉRATIONS DU CONSEIL MUNICIPAL. Séance du 12 mars 2026. "
             "Délibération n° 12. Le conseil municipal, après en avoir délibéré, adopte. Le maire (signé)")
    s1, _ = traiter_seance(date(2026, 3, 12), [PieceBrute(texte)])
    s2, _ = traiter_seance(date(2026, 4, 9), [PieceBrute(texte.replace("12 mars", "9 avril"))])
    assert s1.docs == {"DELIB"}
    note = calculer(Collectivite("commune", 44194), [s1, s2], date(2026, 1, 1), date(2026, 6, 30))
    pv12 = [l for l in note.lignes if l.obligation == "PV-12" and l.occurrence.startswith("2026-03-12")]
    assert pv12 and pv12[0].resultat == NON                      # lecture stricte (DN-13, P65)
