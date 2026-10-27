-- Schéma PostgreSQL du projet Tandem / Score Citoyen (v0.1, 22/10/2026)
-- Principes : archive d'abord (P58) ; faits séparés des constats ; règles versionnées ; historique conservé (P14).
-- Les tables d'événements sont en ajout seul : on ne met jamais à jour un constat, on en insère un nouveau.

CREATE SCHEMA IF NOT EXISTS tandem;
SET search_path = tandem;

CREATE TYPE type_collectivite AS ENUM ('commune','communaute_communes','communaute_agglomeration','communaute_urbaine','metropole');
CREATE TYPE resultat AS ENUM ('oui','non','non_applicable','a_verifier','non_evaluable');
CREATE TYPE passe_extraction AS ENUM ('regles','ia','humain');
CREATE TYPE statut_document AS ENUM ('en_ligne','disparu');
CREATE TYPE statut_obligation AS ENUM ('calcule','information','exclu');
CREATE TYPE statut_relecture AS ENUM ('en_attente','en_cours','tranchee','abandonnee');

-- Référentiel -------------------------------------------------------------
CREATE TABLE collectivite (
  id               text PRIMARY KEY,               -- SIREN ; code INSEE dans insee_code pour les communes
  insee_code       text UNIQUE,
  type             type_collectivite NOT NULL,
  nom              text NOT NULL,
  population       integer NOT NULL CHECK (population >= 0),
  population_millesime integer NOT NULL,
  epci_id          text REFERENCES collectivite(id),  -- rattachement d'une commune à son intercommunalité
  regime_particulier text,                           -- non null = non évalué dans la première version (P62)
  site_url         text,
  codes_postaux    text[] NOT NULL DEFAULT '{}',
  CHECK (type = 'commune' OR epci_id IS NULL)
);
CREATE INDEX collectivite_cp_idx ON collectivite USING gin (codes_postaux);
CREATE INDEX collectivite_epci_idx ON collectivite (epci_id);

CREATE TABLE competence_exercee (               -- BANATIC (P27)
  collectivite_id text NOT NULL REFERENCES collectivite(id),
  competence      text NOT NULL,                  -- déchets, eau, assainissement, plu, bruit, ...
  exercee         boolean NOT NULL,
  source          text NOT NULL,
  releve_le       date NOT NULL,
  PRIMARY KEY (collectivite_id, competence, releve_le)
);

-- Règles ------------------------------------------------------------------
CREATE TABLE version_methode (
  version         text PRIMARY KEY,               -- '1.0', '1.1' ...
  publiee_le      date NOT NULL,
  description     text NOT NULL
);

CREATE TABLE obligation (
  id              text NOT NULL,                  -- ACT-002-D, PV-05 ...
  version         text NOT NULL REFERENCES version_methode(version),
  libelle         text NOT NULL,
  axe             text,
  module          text NOT NULL,                  -- SOCLE, M1000, M3500, FAIT, ARRETE_BRUIT ...
  occurrence      text NOT NULL,
  texte           text NOT NULL,
  statut          statut_obligation NOT NULL,
  document        text,
  condition       text NOT NULL DEFAULT 'aucune' CHECK (condition IN ('aucune','fait','evenement')),
  delai           text,
  PRIMARY KEY (id, version)
);

-- Collecte ----------------------------------------------------------------
CREATE TABLE passage (
  id              serial PRIMARY KEY,
  numero          integer NOT NULL,               -- 0 = passage initial, 1 à 4 = mises à jour (pilote, DN-08)
  campagne        text NOT NULL,                  -- 'pilote-salon-2026'
  debut           timestamptz NOT NULL,
  fin             timestamptz,
  UNIQUE (campagne, numero)
);

CREATE TABLE archive (
  id              bigserial PRIMARY KEY,
  sha256          text NOT NULL,
  url             text NOT NULL,
  capture_le      timestamptz NOT NULL DEFAULT now(),
  passage_id      integer REFERENCES passage(id),
  http_status     integer,
  mime            text,
  taille          bigint,
  stockage_cle    text NOT NULL,                  -- clé dans le stockage objet
  UNIQUE (sha256, url)
);

CREATE TABLE document (
  id              bigserial PRIMARY KEY,
  collectivite_id text NOT NULL REFERENCES collectivite(id),
  type_document   text NOT NULL,                  -- PV, DELIB, LISTE, ROB, RI ...
  seance_date     date,
  url             text NOT NULL,
  date_ecrite     date,                           -- date écrite sur l'acte (P40c)
  premiere_detection timestamptz NOT NULL,
  derniere_observation timestamptz NOT NULL,
  statut          statut_document NOT NULL DEFAULT 'en_ligne',
  page_hote       text,                           -- page qui listait le document : sa relecture réussie prouve une disparition (P54)
  archive_id      bigint NOT NULL REFERENCES archive(id),
  UNIQUE (collectivite_id, url)
);
CREATE INDEX document_coll_type_idx ON document (collectivite_id, type_document, seance_date);

CREATE TABLE observation_document (             -- une ligne par document et par passage : base de la disparition (P54)
  document_id     bigint NOT NULL REFERENCES document(id),
  passage_id      integer NOT NULL REFERENCES passage(id),
  presente        boolean NOT NULL,
  PRIMARY KEY (document_id, passage_id)
);

CREATE TABLE seance (
  id              bigserial PRIMARY KEY,
  collectivite_id text NOT NULL REFERENCES collectivite(id),
  date            date NOT NULL,
  attendue        boolean NOT NULL DEFAULT false, -- P56 : séance attendue (trimestre sans aucun document)
  source          text NOT NULL,
  UNIQUE (collectivite_id, date, attendue)
);

-- Extraction --------------------------------------------------------------
CREATE TABLE fait (
  id              bigserial PRIMARY KEY,
  document_id     bigint NOT NULL REFERENCES document(id),
  cle             text NOT NULL,                  -- 'mention_signature', 'nb_deliberations_citees', ...
  valeur          jsonb NOT NULL,
  extrait         text,                           -- phrase source conservée
  page            integer,
  passe           passe_extraction NOT NULL,
  confiance       numeric(4,3) CHECK (confiance BETWEEN 0 AND 1),
  version_extracteur text NOT NULL,
  cree_le         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX fait_doc_idx ON fait (document_id, cle);

CREATE TABLE relecture (
  id              bigserial PRIMARY KEY,
  fait_id         bigint REFERENCES fait(id),
  document_id     bigint NOT NULL REFERENCES document(id),
  question        text NOT NULL,
  motif_selection text NOT NULL,                  -- sélection par l'IA : confiance basse, illisible, contradiction
  statut          statut_relecture NOT NULL DEFAULT 'en_attente',
  decision        resultat,
  relecteur       text,
  decide_le       timestamptz,
  commentaire     text
);
CREATE INDEX relecture_file_idx ON relecture (statut, id);

-- Constats et notes -------------------------------------------------------
CREATE TABLE constat (
  id              bigserial PRIMARY KEY,
  collectivite_id text NOT NULL REFERENCES collectivite(id),
  obligation_id   text NOT NULL,
  version_methode text NOT NULL REFERENCES version_methode(version),
  occurrence_cle  text NOT NULL DEFAULT '',       -- date de séance, exercice, identifiant de marché...
  resultat        resultat NOT NULL,
  preuve_fait_ids bigint[] NOT NULL DEFAULT '{}',
  preuve_archive_ids bigint[] NOT NULL DEFAULT '{}',
  explication     text,
  calcule_le      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (obligation_id, version_methode) REFERENCES obligation(id, version)
);
CREATE INDEX constat_coll_idx ON constat (collectivite_id, obligation_id, occurrence_cle, calcule_le DESC);

CREATE TABLE note (
  id              bigserial PRIMARY KEY,
  collectivite_id text NOT NULL REFERENCES collectivite(id),
  version_methode text NOT NULL REFERENCES version_methode(version),
  calculee_le     timestamptz NOT NULL DEFAULT now(),
  fenetre_debut   date NOT NULL,
  fenetre_fin     date NOT NULL,
  note_globale    numeric(5,2),                   -- null si aucune obligation évaluable
  nb_oui          integer NOT NULL,
  nb_non          integer NOT NULL,
  nb_a_verifier   integer NOT NULL,
  nb_non_applicable integer NOT NULL,
  couverture      numeric(5,2) NOT NULL,
  detail_axes     jsonb NOT NULL                  -- {axe: {note, oui, non, a_verifier, couverture}}
);
CREATE INDEX note_coll_idx ON note (collectivite_id, calculee_le DESC);

-- Droit de réponse --------------------------------------------------------
CREATE TABLE droit_de_reponse (
  id              bigserial PRIMARY KEY,
  collectivite_id text NOT NULL REFERENCES collectivite(id),
  recu_le         timestamptz NOT NULL DEFAULT now(),
  objet           text NOT NULL,
  contenu         text NOT NULL,
  traite_le       timestamptz,
  suite           text,
  public          boolean NOT NULL DEFAULT true
);

-- Vue : dernier constat par (collectivité, obligation, occurrence)
CREATE VIEW constat_courant AS
SELECT DISTINCT ON (collectivite_id, obligation_id, occurrence_cle) *
FROM constat
ORDER BY collectivite_id, obligation_id, occurrence_cle, calcule_le DESC, id DESC;

-- Personnes privées (DN-34, DN-36 à DN-38) : repère stable (A, B, ...) par collectivité.
-- Le NOM n'est JAMAIS exporté : table privée. Le citoyen voit le repère et les documents sources,
-- où le nom figure (copies archivées intactes).
CREATE TABLE personne_privee (                     -- PRIVÉE : hors de l'export et de la base ouverte
  collectivite_id text NOT NULL REFERENCES collectivite(id),
  repere          text NOT NULL,                   -- 'A', 'B', ... 'AA'
  nom_source      text NOT NULL,                   -- tel qu'écrit dans un document (preuve interne)
  a_rapprocher_de text,                            -- repère à examiner par un relecteur (jamais fusionné seul)
  PRIMARY KEY (collectivite_id, repere)
);
CREATE TABLE personne_citation (                   -- publique : repère + document, sans nom
  collectivite_id text NOT NULL,
  repere          text NOT NULL,
  document_id     bigint NOT NULL REFERENCES document(id),
  page            integer NOT NULL DEFAULT 0,
  PRIMARY KEY (collectivite_id, repere, document_id, page),
  FOREIGN KEY (collectivite_id, repere) REFERENCES personne_privee(collectivite_id, repere)
);
CREATE VIEW personne_signalee AS                   -- bloc public de la fiche : même personne citée souvent
SELECT collectivite_id, repere, count(DISTINCT document_id) AS nb_documents,
       array_agg(DISTINCT document_id ORDER BY document_id) AS documents
FROM personne_citation
GROUP BY collectivite_id, repere
HAVING count(DISTINCT document_id) >= 3;           -- seuil DN-37 (proposé), à garder égal à SEUIL_SIGNALEMENT
