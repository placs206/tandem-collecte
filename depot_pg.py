"""Écriture d'un passage de collecte dans PostgreSQL (schema.sql) : archive, document, observation_document.

Règles (P54, P58, DN-10) :
- une ligne `observation_document` n'existe que si l'état est CONNU (présent, ou disparu prouvé) ;
  une page illisible, bloquée ou interdite par robots.txt ne produit aucune observation (« non constatable »).
- un document est « disparu » seulement si la page qui le listait a été relue avec succès et ne le liste plus.
- les archives ne sont jamais modifiées ; une version modifiée d'un document crée une nouvelle archive.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from collecte import Observation


def enregistrer_passage(conn, campagne: str, numero: int, collectivite_id: str,
                        observations: List[Observation], index_archive: List[dict],
                        debut: datetime, fin: Optional[datetime] = None) -> dict:
    cur = conn.cursor()
    cur.execute("SET search_path = tandem, public")
    cur.execute("""INSERT INTO passage (numero, campagne, debut, fin) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (campagne, numero) DO UPDATE SET fin = EXCLUDED.fin
                   RETURNING id""", (numero, campagne, debut, fin))
    passage_id = cur.fetchone()[0]

    archive_id = {}
    for e in index_archive:
        cur.execute("""INSERT INTO archive (sha256, url, capture_le, passage_id, http_status, mime, taille, stockage_cle)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (sha256, url) DO UPDATE SET sha256 = EXCLUDED.sha256
                       RETURNING id""", (e["sha256"], e["url"], e["capture_le"], passage_id, e["http"],
                                         e["mime"], e["taille"], e["cle"]))
        archive_id[(e["sha256"], e["url"])] = cur.fetchone()[0]

    presentes, pages_lues = set(), set()
    n_presents = n_disparus = 0
    for o in observations:
        if o.statut != "present":
            continue
        if not o.est_document:
            pages_lues.add(o.url)
            continue
        presentes.add(o.url)
        a_id = archive_id.get((o.sha256, o.url))
        if a_id is None:
            cur.execute("SELECT id FROM archive WHERE sha256=%s AND url=%s", (o.sha256, o.url))
            a_id = cur.fetchone()[0]
        cur.execute("""INSERT INTO document (collectivite_id, type_document, url, premiere_detection,
                                             derniere_observation, statut, page_hote, archive_id)
                       VALUES (%s,'A_TYPER',%s, %s, %s,'en_ligne',%s,%s)
                       ON CONFLICT (collectivite_id, url) DO UPDATE
                         SET derniere_observation = EXCLUDED.derniere_observation, statut = 'en_ligne',
                             page_hote = EXCLUDED.page_hote, archive_id = EXCLUDED.archive_id
                       RETURNING id""", (collectivite_id, o.url, debut, debut, o.page_hote, a_id))
        doc_id = cur.fetchone()[0]
        cur.execute("""INSERT INTO observation_document (document_id, passage_id, presente) VALUES (%s,%s,true)
                       ON CONFLICT (document_id, passage_id) DO UPDATE SET presente = true""", (doc_id, passage_id))
        n_presents += 1

    # Documents connus mais non retrouvés : « disparu » seulement si la page hôte a été relue (P54)
    cur.execute("""SELECT id, url, page_hote FROM document
                   WHERE collectivite_id = %s AND statut = 'en_ligne'""", (collectivite_id,))
    for doc_id, url, hote in cur.fetchall():
        if url in presentes:
            continue
        if hote and hote in pages_lues:
            cur.execute("""INSERT INTO observation_document (document_id, passage_id, presente) VALUES (%s,%s,false)
                           ON CONFLICT (document_id, passage_id) DO UPDATE SET presente = false""",
                        (doc_id, passage_id))
            cur.execute("UPDATE document SET statut = 'disparu' WHERE id = %s", (doc_id,))
            n_disparus += 1
    conn.commit()
    non_constatables = sum(1 for o in observations if o.statut == "non_constatable")
    return {"passage_id": passage_id, "presents": n_presents, "disparus": n_disparus,
            "non_constatables": non_constatables}
