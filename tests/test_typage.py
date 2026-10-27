import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typage import typer, vaut_liste_deliberations, vaut_pv  # noqa: E402

PV = """PROCÈS-VERBAL DE LA SÉANCE DU CONSEIL MUNICIPAL du 12 mars 2026
Le maire a ouvert la séance à 18h30. Après discussion, M. Durand prend la parole.
Les débats portent sur le budget. La séance est levée à 21h."""

EXTRAIT = """EXTRAIT DU REGISTRE DES DÉLIBÉRATIONS DU CONSEIL MUNICIPAL
Séance du 12 mars 2026. Délibération n° 12. Le conseil municipal, après en avoir délibéré, adopte."""

ODJ = """CONSEIL MUNICIPAL DU 12 MARS 2026
ORDRE DU JOUR
1. Approbation du procès-verbal de la séance du 5 février
2. Budget primitif"""

CONVOC = """Mesdames, Messieurs les conseillers, vous êtes convoqués en séance le 12 mars 2026."""

LISTE = """LISTE DES DÉLIBÉRATIONS examinées par le conseil municipal du 12 mars 2026
1. Budget primitif 2. Subventions"""


def test_pv_complet():
    r = typer(PV)
    assert r.type == "PV" and not r.douteux and vaut_pv(r.type)


def test_extrait_registre_ne_vaut_pas_pv():
    r = typer(EXTRAIT)
    assert r.type == "EXTRAIT_REGISTRE" and not vaut_pv(r.type)


def test_ordre_du_jour_citant_le_pv_n_est_pas_un_pv():
    r = typer(ODJ)
    assert r.type == "ORDRE_DU_JOUR"


def test_nom_de_fichier_trompeur_ne_decide_pas():
    # un ordre du jour nommé « proces_verbal.pdf » reste un ordre du jour
    r = typer(ODJ, nom_fichier="proces_verbal_mars.pdf")
    assert r.type == "ORDRE_DU_JOUR"


def test_convocation():
    assert typer(CONVOC).type == "CONVOCATION"


def test_liste_deliberations_sans_ambiguite():
    r = typer(LISTE)
    assert r.type == "LISTE_DELIB" and vaut_liste_deliberations(r.type)


def test_ordre_du_jour_ne_vaut_pas_liste():
    assert not vaut_liste_deliberations(typer(ODJ).type)


def test_ambiguite_liste_odj_tranchee_par_la_date():
    texte = "LISTE DES DÉLIBÉRATIONS - ORDRE DU JOUR du conseil du 12 mars 2026\n1. Budget"
    avant = typer(texte, date_piece=date(2026, 3, 5), date_seance=date(2026, 3, 12))
    apres = typer(texte, date_piece=date(2026, 3, 20), date_seance=date(2026, 3, 12))
    assert avant.type == "ORDRE_DU_JOUR"
    assert apres.type == "LISTE_DELIB"


def test_ambiguite_sans_date_part_en_relecture():
    texte = "LISTE DES DÉLIBÉRATIONS - ORDRE DU JOUR du conseil du 12 mars 2026\n1. Budget"
    r = typer(texte)
    assert r.type == "INCONNU" and r.douteux


def test_texte_vide_ou_sans_indice_est_douteux():
    assert typer("").douteux
    r = typer("Bonjour, voici un document quelconque sans rapport.")
    assert r.type == "INCONNU" and r.douteux


def test_delib_isolee():
    t = "Délibération n° 45\nLe conseil municipal, après en avoir délibéré, décide de ..."
    assert typer(t).type == "DELIB"
