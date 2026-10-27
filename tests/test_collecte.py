import hashlib
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from collecte import (Config, DepotFichiers, Navigateur, comparer_passages,  # noqa: E402
                      extraire_liens, parcourir)

PDF1 = b"%PDF-1.4 proces-verbal seance 1"
PDF2 = b"%PDF-1.4 proces-verbal seance 2"


class Site(BaseHTTPRequestHandler):
    etat = {"pages": {}, "robots": "User-agent: *\nDisallow: /prive\n", "status_force": {}, "hits": []}

    def log_message(self, *a):
        pass

    def do_GET(self):
        Site.etat["hits"].append(self.path)
        if self.path in Site.etat["status_force"]:
            self.send_response(Site.etat["status_force"][self.path]); self.end_headers(); return
        if self.path == "/robots.txt":
            r = Site.etat["robots"]
            if r is None:
                self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
            self.wfile.write(r.encode()); return
        corps = Site.etat["pages"].get(self.path)
        if corps is None:
            self.send_response(404); self.end_headers(); return
        mime = "application/pdf" if self.path.endswith(".pdf") else "text/html; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", mime); self.end_headers()
        self.wfile.write(corps if isinstance(corps, bytes) else corps.encode())


@pytest.fixture()
def serveur():
    Site.etat = {"pages": {
        "/": '<a href="/conseil">Conseil municipal</a> <a href="/prive/secret">Zone privée conseil</a>'
             '<a href="/contact">Contact</a>',
        "/conseil": '<a href="/docs/pv1.pdf">PV séance 1</a> <a href="/docs/pv2.pdf">PV séance 2</a>',
        "/docs/pv1.pdf": PDF1, "/docs/pv2.pdf": PDF2,
        "/prive/secret": "interdit",
    }, "robots": "User-agent: *\nDisallow: /prive\n", "status_force": {}, "hits": []}
    srv = HTTPServer(("127.0.0.1", 0), Site)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def cfg(**kw):
    return Config(delai=0.0, **kw)


def test_archive_intacte_et_empreinte(serveur, tmp_path):
    depot = DepotFichiers(str(tmp_path))
    obs = parcourir([serveur + "/"], depot, cfg())
    docs = {o.url: o for o in obs if o.est_document}
    assert set(docs) == {serveur + "/docs/pv1.pdf", serveur + "/docs/pv2.pdf"}
    assert docs[serveur + "/docs/pv1.pdf"].sha256 == hashlib.sha256(PDF1).hexdigest()
    fichier = next(e["cle"] for e in depot.index if e["sha256"] == hashlib.sha256(PDF1).hexdigest())
    assert open(fichier, "rb").read() == PDF1                     # octets identiques à ceux publiés


def test_robots_txt_respecte(serveur, tmp_path):
    parcourir([serveur + "/"], DepotFichiers(str(tmp_path)), cfg())
    assert "/prive/secret" not in Site.etat["hits"]
    obs = parcourir([serveur + "/"], DepotFichiers(str(tmp_path)), cfg())
    interdit = [o for o in obs if o.url.endswith("/prive/secret")]
    assert interdit and interdit[0].statut == "non_constatable" and interdit[0].raison == "interdit_par_robots"


def test_robots_injoignable_on_s_abstient(serveur, tmp_path):
    Site.etat["status_force"]["/robots.txt"] = 500
    obs = parcourir([serveur + "/"], DepotFichiers(str(tmp_path)), cfg())
    assert obs and all(o.statut == "non_constatable" for o in obs)
    assert Site.etat["hits"] == ["/robots.txt"]                    # aucune page demandée


def test_blocage_403_n_est_pas_un_non(serveur, tmp_path):
    Site.etat["status_force"]["/docs/pv2.pdf"] = 403
    obs = parcourir([serveur + "/"], DepotFichiers(str(tmp_path)), cfg())
    bloque = [o for o in obs if o.url.endswith("pv2.pdf")][0]
    assert bloque.statut == "non_constatable" and bloque.raison == "bloque_403"


def test_delai_entre_requetes_sur_le_meme_hote():
    attentes = []
    t = [0.0]
    nav = Navigateur(Config(delai=2.0), dormir=lambda s: (attentes.append(s), t.__setitem__(0, t[0] + s)),
                     horloge=lambda: t[0])
    nav._attendre("h"); nav._attendre("h"); nav._attendre("h")
    assert attentes == [2.0, 2.0]                                  # 1re requête immédiate, puis 2 s


def test_extraire_liens_absolus_et_sans_ancres():
    liens = extraire_liens('<a href="a.pdf">A</a><a href="#x">x</a><a href="mailto:a@b">m</a>', "http://h/dir/")
    assert liens == [("http://h/dir/a.pdf", "A")]


def test_disparition_constatee_seulement_si_page_hote_relue(serveur, tmp_path):
    avant = parcourir([serveur + "/"], DepotFichiers(str(tmp_path)), cfg())
    # le PV 1 est retiré de la page « conseil »
    Site.etat["pages"]["/conseil"] = '<a href="/docs/pv2.pdf">PV séance 2</a>'
    apres = parcourir([serveur + "/"], DepotFichiers(str(tmp_path)), cfg())
    etat = comparer_passages(avant, apres)
    assert etat[serveur + "/docs/pv1.pdf"] == "disparu"
    assert etat[serveur + "/docs/pv2.pdf"] == "present"


def test_page_hote_illisible_donne_non_constatable(serveur, tmp_path):
    avant = parcourir([serveur + "/"], DepotFichiers(str(tmp_path)), cfg())
    Site.etat["status_force"]["/conseil"] = 500                    # la page qui listait les PV est en panne
    apres = parcourir([serveur + "/"], DepotFichiers(str(tmp_path)), cfg())
    etat = comparer_passages(avant, apres)
    assert set(etat.values()) == {"non_constatable"}               # jamais « disparu » sur une panne


def test_document_modifie_garde_les_deux_versions(serveur, tmp_path):
    depot = DepotFichiers(str(tmp_path))
    parcourir([serveur + "/"], depot, cfg())
    Site.etat["pages"]["/docs/pv1.pdf"] = PDF1 + b" modifie"
    parcourir([serveur + "/"], depot, cfg())
    hashes = {e["sha256"] for e in depot.index if e["url"].endswith("pv1.pdf")}
    assert len(hashes) == 2                                        # la preuve de la 1re version est conservée
