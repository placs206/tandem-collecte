import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from constats import Fait, resultat_faits  # noqa: E402
from engine import AV, NON, OUI  # noqa: E402
from extraction_ia import construire_consigne, fusionner, lire  # noqa: E402

TEXTE = "Procès-verbal. Le maire, Claire Dupont, signé le 13 mars. Le quorum étant atteint, la séance est ouverte."


class Faux:
    def __init__(self, reponse):
        self.reponse, self.consignes = reponse, []

    def completer(self, consigne):
        self.consignes.append(consigne)
        return self.reponse if isinstance(self.reponse, str) else "Voici : " + json.dumps(self.reponse)


def rep(valeur=True, extrait="", conf=0.95, raison=None):
    return {"valeur": valeur, "extrait": extrait, "page": 1, "confiance": conf, "raison_du_doute": raison}


def test_consigne_sans_note_ni_conclusion():
    c = construire_consigne(TEXTE, ["quorum", "signature_ou_mention_signe"])
    for interdit in ("note", "conforme", "obligation", "pénalité", "score"):
        assert interdit not in c.lower().replace("noter", "")
    assert "mot pour mot" in c


def test_fait_valide_avec_citation_exacte():
    c = Faux({"quorum": rep(True, "Le quorum étant atteint")})
    r = lire(TEXTE, ["quorum"], c)
    assert r.faits["quorum"].valeur is True and not r.douteux


def test_citation_introuvable_rejette_le_fait():
    r = lire(TEXTE, ["quorum"], Faux({"quorum": rep(True, "Le quorum est largement dépassé")}))
    assert r.faits["quorum"].valeur is None and r.faits["quorum"].douteux
    assert "introuvable" in r.douteux[0]["motif"]
    assert resultat_faits(r.faits, ["quorum"]) == AV                # jamais « oui » sur une citation inventée


def test_confiance_faible_est_douteuse():
    r = lire(TEXTE, ["quorum"], Faux({"quorum": rep(True, "Le quorum étant atteint", conf=0.6)}))
    assert r.faits["quorum"].douteux and resultat_faits(r.faits, ["quorum"]) == AV


def test_valeur_vraie_sans_citation_est_douteuse():
    r = lire(TEXTE, ["quorum"], Faux({"quorum": rep(True, "")}))
    assert r.faits["quorum"].douteux


def test_reponse_illisible_ou_incomplete():
    r = lire(TEXTE, ["quorum", "heure"], Faux("Je ne peux pas répondre."))
    assert all(f.douteux and f.valeur is None for f in r.faits.values())
    r2 = lire(TEXTE, ["quorum", "heure"], Faux({"quorum": rep(True, "Le quorum étant atteint")}))
    assert r2.faits["heure"].douteux and not r2.faits["quorum"].douteux


def test_contradiction_avec_la_passe_1():
    p1 = {"signature_ou_mention_signe": Fait("signature_ou_mention_signe", True)}
    r = lire(TEXTE, ["signature_ou_mention_signe"],
             Faux({"signature_ou_mention_signe": rep(False, "", 0.9)}), passe1=p1)
    assert r.faits["signature_ou_mention_signe"].douteux
    assert "contradiction" in r.douteux[0]["motif"]


def test_absence_affirmee_par_l_ia_a_confirmer_par_un_humain_dn48():
    ia = lire(TEXTE, ["heure"], Faux({"heure": rep(False, "", 0.95)}))
    assert ia.faits["heure"].douteux and resultat_faits(ia.faits, ["heure"]) == AV   # pas de « non » sans humain
    ia.faits["heure"].tranche = False                                                  # relecteur confirme l'absence
    assert resultat_faits(ia.faits, ["heure"]) == NON
    p1 = {"quorum": Fait("quorum", True), "heure": Fait("heure", None)}
    fus = fusionner(p1, ia)
    assert fus["quorum"].valeur is True and fus["heure"].valeur is False
    assert resultat_faits({"quorum": fus["quorum"]}, ["quorum"]) == OUI
