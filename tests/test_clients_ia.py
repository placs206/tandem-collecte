import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from clients_ia import AttenteReponse, ClientAnthropic, ClientManuel, ClientOpenAI  # noqa: E402
from constats import resultat_faits  # noqa: E402
from engine import AV, OUI  # noqa: E402
from extraction_ia import lire, lire_double  # noqa: E402

TEXTE = "Le quorum étant atteint, la séance est ouverte sous la présidence de Mme Dupont."
REP = {"quorum": {"valeur": True, "extrait": "Le quorum étant atteint", "page": 1, "confiance": 0.95,
                  "raison_du_doute": None}}


def test_client_manuel_aller_retour(tmp_path):
    c = ClientManuel(str(tmp_path))
    with pytest.raises(AttenteReponse) as e:
        lire(TEXTE, ["quorum"], c)
    assert os.path.exists(e.value.fichier_consigne) and "mot pour mot" in open(e.value.fichier_consigne).read()
    open(e.value.fichier_reponse, "w").write("Voici la réponse : " + json.dumps(REP))   # collée depuis ChatGPT
    r = lire(TEXTE, ["quorum"], c)
    assert resultat_faits(r.faits, ["quorum"]) == OUI


def test_reponse_collee_modifiee_citation_inventee_rejetee(tmp_path):
    c = ClientManuel(str(tmp_path))
    with pytest.raises(AttenteReponse) as e:
        lire(TEXTE, ["quorum"], c)
    faux = json.loads(json.dumps(REP)); faux["quorum"]["extrait"] = "Le quorum est dépassé"
    open(e.value.fichier_reponse, "w").write(json.dumps(faux))
    assert resultat_faits(lire(TEXTE, ["quorum"], c).faits, ["quorum"]) == AV


class Api(BaseHTTPRequestHandler):
    vus = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Api.vus.append((self.path, dict(self.headers), corps))
        if self.path.endswith("/chat/completions"):
            rep = {"choices": [{"message": {"content": json.dumps(REP)}}],
                   "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        else:
            rep = {"content": [{"type": "text", "text": json.dumps(REP)}],
                   "usage": {"input_tokens": 90, "output_tokens": 15}}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(rep).encode())


@pytest.fixture()
def api():
    Api.vus = []
    srv = HTTPServer(("127.0.0.1", 0), Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_client_openai(api):
    c = ClientOpenAI(modele="modele-x", api_key="cle-test", base_url=api)
    assert resultat_faits(lire(TEXTE, ["quorum"], c).faits, ["quorum"]) == OUI
    chemin, entetes, corps = Api.vus[0]
    assert entetes["Authorization"] == "Bearer cle-test" and corps["model"] == "modele-x"
    assert corps["temperature"] == 0 and (c.jetons_entree, c.jetons_sortie) == (100, 20)


def test_client_anthropic(api):
    c = ClientAnthropic(modele="modele-y", api_key="cle-test", base_url=api)
    assert resultat_faits(lire(TEXTE, ["quorum"], c).faits, ["quorum"]) == OUI
    chemin, entetes, corps = Api.vus[0]
    assert entetes["X-Api-Key"] == "cle-test" and entetes["Anthropic-Version"] == "2023-06-01"
    assert corps["max_tokens"] > 0 and (c.jetons_entree, c.jetons_sortie) == (90, 15)


def test_cle_et_modele_obligatoires(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TANDEM_MODELE_OPENAI", raising=False)
    with pytest.raises(ValueError):
        ClientOpenAI()
    with pytest.raises(ValueError):
        ClientOpenAI(modele="m")


class Fixe:
    def __init__(self, rep):
        self.rep = rep

    def completer(self, consigne):
        return json.dumps(self.rep)


def test_double_lecture_accord_et_desaccord():
    ok = Fixe(REP)
    r = lire_double(TEXTE, ["quorum"], ok, Fixe(REP))
    assert not r.douteux and resultat_faits(r.faits, ["quorum"]) == OUI
    autre = json.loads(json.dumps(REP)); autre["quorum"]["valeur"] = False; autre["quorum"]["extrait"] = ""
    r2 = lire_double(TEXTE, ["quorum"], ok, Fixe(autre))
    assert r2.douteux and "désaccord" in r2.douteux[0]["motif"]
    assert resultat_faits(r2.faits, ["quorum"]) == AV               # désaccord : jamais compté, relecture
