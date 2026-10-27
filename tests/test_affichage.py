import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from affichage import MASQUE_TIERS, afficher_personne, pseudonymiser_nom  # noqa: E402


def test_formes_courantes():
    assert pseudonymiser_nom("Claire Dupont") == "C. DUPONT"
    assert pseudonymiser_nom("Madame Claire Dupont") == "Mme C. DUPONT"
    assert pseudonymiser_nom("M. Jean-Pierre Martin") == "M. J. MARTIN"
    assert pseudonymiser_nom("Mademoiselle Léa Roux") == "Mme L. ROUX"
    assert pseudonymiser_nom("DUPONT Claire") == "C. DUPONT"
    assert pseudonymiser_nom("Éric Lefèvre") == "É. LEFÈVRE"


def test_civilite_conservee_et_normalisee_jamais_devinee():
    r = pseudonymiser_nom("Monsieur Claude Dupont")
    assert "Claude" not in r and "Monsieur" not in r and r == "M. C. DUPONT"
    # prénom épicène sans civilité dans la source : on ne devine pas le genre
    assert pseudonymiser_nom("Claude Dupont") == "C. DUPONT"


def test_un_seul_mot():
    assert pseudonymiser_nom("Dupont") == "DUPONT"
    assert pseudonymiser_nom("Madame Dupont") == "Mme DUPONT"


def test_tiers_masques():
    assert afficher_personne("Claire Dupont", est_elu_ou_agent=False) == MASQUE_TIERS
    assert afficher_personne("Madame Claire Dupont", est_elu_ou_agent=True) == "Mme C. DUPONT"
