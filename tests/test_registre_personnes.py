import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from affichage import RegistrePersonnes, lettre  # noqa: E402


def test_lettres():
    assert [lettre(i) for i in (0, 1, 25, 26, 27, 51, 52)] == ["A", "B", "Z", "AA", "AB", "AZ", "BA"]


def test_meme_personne_meme_lettre_quelle_que_soit_l_ecriture():
    r = RegistrePersonnes("SIREN1")
    a = r.repere("Madame Claire Dupont", 1)
    b = r.repere("DUPONT Claire", 2)
    c = r.repere("claire  dupont", 3)
    assert a == b == c == "[personne privée A]"
    assert r.repere("Paul Martin", 3) == "[personne privée B]"


def test_registres_independants_par_collectivite():
    r1, r2 = RegistrePersonnes("SIREN1"), RegistrePersonnes("SIREN2")
    r1.repere("Paul Martin", 1)
    assert r1.repere("Claire Dupont", 1) == "[personne privée B]"
    assert r2.repere("Claire Dupont", 1) == "[personne privée A]"


def test_signalement_public_sans_nom_a_partir_du_seuil():
    r = RegistrePersonnes("SIREN1")
    for doc in (10, 11, 12):
        r.repere("Claire Dupont", doc)
    r.repere("Paul Martin", 10)
    sig = r.signalements()
    assert sig == [{"repere": "[personne privée A]", "nb_documents": 3, "documents": [10, 11, 12]}]
    assert "Dupont" not in str(sig) and "Claire" not in str(sig)


def test_citations_repetees_dans_un_meme_document_comptent_une_fois():
    r = RegistrePersonnes("SIREN1")
    for page in (1, 2, 3, 4):
        r.repere("Claire Dupont", 10, page)
    assert r.signalements() == []


def test_pas_de_fusion_automatique_mais_rapprochement_propose():
    r = RegistrePersonnes("SIREN1")
    a = r.repere("Claire Dupont", 1)
    b = r.repere("C. Dupont", 2)
    assert a != b                                        # jamais fusionnées sans relecture
    assert r.rapprochements_possibles() == [(a, b)]
    r.repere("Paul Martin", 3)
    assert len(r.rapprochements_possibles()) == 1
