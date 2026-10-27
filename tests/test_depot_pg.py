import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

psycopg2 = pytest.importorskip("psycopg2")

from collecte import DepotFichiers, parcourir  # noqa: E402
from depot_pg import enregistrer_passage  # noqa: E402
from test_collecte import PDF1, Site, cfg, serveur  # noqa: E402,F401

HOTE, USER = "/home/pgtest/pgd", "pgtest"
SCHEMA = os.path.join(os.path.dirname(__file__), "..", "schema.sql")


@pytest.fixture()
def base():
    try:
        admin = psycopg2.connect(host=HOTE, user=USER, dbname="postgres")
    except Exception:
        pytest.skip("PostgreSQL local indisponible")
    admin.autocommit = True
    nom = "t_" + uuid.uuid4().hex[:10]
    admin.cursor().execute(f"CREATE DATABASE {nom}")
    conn = psycopg2.connect(host=HOTE, user=USER, dbname=nom)
    conn.cursor().execute(open(SCHEMA, encoding="utf-8").read())
    conn.cursor().execute("""INSERT INTO tandem.collectivite (id, insee_code, type, nom, population, population_millesime)
                             VALUES ('211301033','13103','commune','Salon-de-Provence',44194,2023)""")
    conn.commit()
    yield conn
    conn.close()
    admin.cursor().execute(f"DROP DATABASE {nom} WITH (FORCE)")
    admin.close()


def passage(conn, serveur, tmp_path, numero):
    depot = DepotFichiers(str(tmp_path / f"p{numero}"))
    obs = parcourir([serveur + "/"], depot, cfg())
    t = datetime(2026, 11, 2 + numero, tzinfo=timezone.utc)
    return enregistrer_passage(conn, "pilote-test", numero, "211301033", obs, depot.index, t, t)


def lignes(conn, sql):
    cur = conn.cursor(); cur.execute(sql); return cur.fetchall()


def test_schema_complet_charge_et_passage_initial(base, serveur, tmp_path):
    r = passage(base, serveur, tmp_path, 0)
    assert r["presents"] == 2 and r["disparus"] == 0
    assert lignes(base, "select count(*) from tandem.document")[0][0] == 2
    assert lignes(base, "select count(*) from tandem.observation_document where presente")[0][0] == 2
    assert lignes(base, "select count(*) from tandem.archive")[0][0] >= 2


def test_disparition_prouvee_puis_document_qui_revient(base, serveur, tmp_path):
    passage(base, serveur, tmp_path, 0)
    Site.etat["pages"]["/conseil"] = '<a href="/docs/pv2.pdf">PV 2</a>'
    r = passage(base, serveur, tmp_path, 1)
    assert r["disparus"] == 1
    assert lignes(base, "select statut from tandem.document where url like '%pv1.pdf'")[0][0] == "disparu"
    assert lignes(base, "select presente from tandem.observation_document o join tandem.document d "
                        "on d.id=o.document_id join tandem.passage p on p.id=o.passage_id "
                        "where d.url like '%pv1.pdf' and p.numero=1")[0][0] is False
    Site.etat["pages"]["/conseil"] = ('<a href="/docs/pv1.pdf">PV 1</a><a href="/docs/pv2.pdf">PV 2</a>')
    passage(base, serveur, tmp_path, 2)
    assert lignes(base, "select statut from tandem.document where url like '%pv1.pdf'")[0][0] == "en_ligne"


def test_page_illisible_n_ecrit_aucune_observation(base, serveur, tmp_path):
    passage(base, serveur, tmp_path, 0)
    Site.etat["status_force"]["/conseil"] = 500
    r = passage(base, serveur, tmp_path, 1)
    assert r["disparus"] == 0 and r["non_constatables"] >= 1
    n = lignes(base, "select count(*) from tandem.observation_document o join tandem.passage p on p.id=o.passage_id "
                     "where p.numero=1")[0][0]
    assert n == 0                                                  # état inconnu : aucune ligne, jamais « non »
    assert lignes(base, "select count(*) from tandem.document where statut='disparu'")[0][0] == 0


def test_version_modifiee_cree_une_nouvelle_archive(base, serveur, tmp_path):
    passage(base, serveur, tmp_path, 0)
    Site.etat["pages"]["/docs/pv1.pdf"] = PDF1 + b" modifie"
    passage(base, serveur, tmp_path, 1)
    n = lignes(base, "select count(distinct sha256) from tandem.archive where url like '%pv1.pdf'")[0][0]
    assert n == 2
