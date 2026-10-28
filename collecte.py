"""Robot de collecte poli (v0.1, 23/10/2026) : DN-09, DN-10, DN-11, P54, P58.

- Points d'entrée configurés à la main pour chaque collectivité (DN-09).
- Respect de robots.txt, une requête toutes les `delai` secondes par hôte, robot identifié, aucun contournement.
  Un blocage (403, 429) ou un robots.txt injoignable rend la page « non constatable » : ce n'est JAMAIS un « non ».
- Chaque document est archivé tel quel (octets intacts) avec son empreinte sha256 (règle d'or, DN-32).
- La disparition d'un document n'est constatée que si la page qui le listait a bien été relue au passage suivant.
"""
from __future__ import annotations

import hashlib
import os
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Dict, List, Optional, Protocol, Set, Tuple
from urllib.parse import quote, urldefrag, urljoin, urlparse, urlsplit, urlunsplit

VERSION_ROBOT = "collecte-0.1"
EXT_DOCUMENTS = (".pdf", ".docx", ".doc", ".odt", ".xlsx", ".xls", ".ods", ".csv", ".txt")
URLS_IGNOREES = ("/recherche", "?s=", "?recherche=", "/feed", "/wp-json", "/tag/")
MOTS_PISTES = ("conseil", "deliberation", "proces", "compte-rendu", "compte_rendu", "seance", "ordre",
               "odj", "budget", "arrete", "publication", "archive", "registre", "rapport", "reglement",
               "commission", "document", "transparence", "democratie")


@dataclass
class Config:
    user_agent: str = "TandemScoreCitoyenBot/0.1 (+contact: a renseigner par l'association)"
    delai: float = 2.0            # secondes entre deux requêtes sur le même hôte (DN-10)
    timeout: float = 20.0
    max_taille: int = 60 * 1024 * 1024
    profondeur_max: int = 3
    pages_max: int = 400          # garde-fou par collectivité et par passage
    duree_max: float = 0.0        # secondes par collectivité (0 = illimité) ; l'arrêt est propre, les observations sont gardées
    verbeux: bool = False
    sans_telechargement: tuple = ()   # fragments d'URL de documents à lister sans les télécharger (ex. 4 000 délibérations d'un portail)
    attente_reprise: float = 5.0   # secondes × essai² entre deux essais (réseau, 5xx)
    sur_observation: object = None   # rappel appelé à chaque observation (écriture immédiate : rien n'est perdu si le passage est coupé)
    hotes_autorises: Set[str] = field(default_factory=set)   # en plus de l'hôte du point d'entrée


@dataclass
class Reponse:
    url: str
    statut: int               # code HTTP ; 0 = erreur réseau
    contenu: bytes = b""
    mime: str = ""
    raison: str = ""


@dataclass
class Observation:
    url: str
    page_hote: str            # page qui listait le document ('' pour un point d'entrée)
    statut: str               # 'present' | 'non_constatable'
    sha256: Optional[str] = None
    mime: str = ""
    taille: int = 0
    raison: str = ""          # pourquoi non constatable (robots, 403, 429, réseau, trop gros…)
    est_document: bool = False
    depose_le_site: str = ""   # date de dépôt déclarée par le site (WordPress : champ « date » du média)


class Depot(Protocol):
    def archiver(self, url: str, contenu: bytes, mime: str, statut_http: int, capture_le: datetime) -> str: ...


class DepotFichiers:
    """Archive sur disque, adressée par empreinte : un fichier n'est jamais réécrit ni modifié."""

    def __init__(self, racine: str):
        self.racine = racine
        self.index: List[dict] = []

    def archiver(self, url: str, contenu: bytes, mime: str, statut_http: int, capture_le: datetime) -> str:
        h = hashlib.sha256(contenu).hexdigest()
        ext = os.path.splitext(urlparse(url).path)[1].lower()[:8] or ".bin"
        chemin = os.path.join(self.racine, h[:2], h[2:4], h + ext)
        if not os.path.exists(chemin):          # jamais d'écrasement
            os.makedirs(os.path.dirname(chemin), exist_ok=True)
            with open(chemin, "xb") as f:
                f.write(contenu)
        self.index.append({"sha256": h, "url": url, "mime": mime, "http": statut_http,
                           "taille": len(contenu), "capture_le": capture_le, "cle": chemin})
        return h


def url_encodee(url: str) -> str:
    """Encode espaces et caractères non ASCII (ex. « N°67 », « Annexe FPIC 2026.pdf ») sans toucher à ce qui l'est déjà."""
    u = urlsplit(url)
    return urlunsplit((u.scheme, u.netloc.encode("idna").decode("ascii"),
                       quote(u.path, safe="/%:@!$&'()*+,;=~-._"),
                       quote(u.query, safe="=&%:@/?+,;~-._!$'()*"), ""))


class _Liens(HTMLParser):
    def __init__(self):
        super().__init__()
        self.liens: List[Tuple[str, str]] = []
        self._href: Optional[str] = None
        self._texte: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            self._href = d.get("href")
            self._texte = []

    def handle_data(self, data):
        if self._href is not None:
            self._texte.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.liens.append((self._href, " ".join("".join(self._texte).split())))
            self._href = None


def extraire_liens(html: str, base: str) -> List[Tuple[str, str]]:
    p = _Liens()
    try:
        p.feed(html)
    except Exception:
        pass
    out = []
    for href, texte in p.liens:
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        out.append((urldefrag(urljoin(base, href))[0], texte))
    return out


class Navigateur:
    """Accès HTTP poli. `horloge` et `dormir` sont injectables pour les tests."""

    def __init__(self, config: Config, dormir=time.sleep, horloge=time.monotonic):
        self.c = config
        self._dormir, self._horloge = dormir, horloge
        self._dernier: Dict[str, float] = {}
        self._robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self.requetes = 0

    def _attendre(self, hote: str) -> None:
        t = self._horloge()
        prochain = self._dernier.get(hote, -1e9) + self.c.delai
        if t < prochain:
            self._dormir(prochain - t)
        self._dernier[hote] = self._horloge()

    def _brut(self, url: str) -> Reponse:
        """Une requête avec reprises : réseau, délai dépassé et 5xx sont retentés (3 essais, attente croissante)."""
        rep = self._une_fois(url)
        for essai in range(1, 4):
            retentable = rep.raison.startswith("reseau:") or rep.statut >= 500   # jamais 403/429 : on n'insiste pas (DN-10)
            if not retentable:
                break
            self._dormir(self.c.attente_reprise * essai * essai)
            rep = self._une_fois(url)
        return rep

    def _une_fois(self, url: str) -> Reponse:
        hote = urlparse(url).netloc
        self._attendre(hote)
        self.requetes += 1
        req = urllib.request.Request(url_encodee(url), headers={"User-Agent": self.c.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.c.timeout) as r:
                contenu = r.read(self.c.max_taille + 1)
                if len(contenu) > self.c.max_taille:
                    return Reponse(url, r.status, b"", r.headers.get("Content-Type", ""), "trop_gros")
                return Reponse(r.geturl(), r.status, contenu, r.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            return Reponse(url, e.code, b"", "", f"http_{e.code}")
        except Exception as e:                      # réseau, DNS, délai dépassé
            return Reponse(url, 0, b"", "", f"reseau:{type(e).__name__}")

    def _regles(self, url: str):
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rep = self._brut(base + "/robots.txt")
            if rep.statut == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(rep.contenu.decode("utf-8", "replace").splitlines())
                self._robots[base] = rp
            elif rep.statut in (404, 410):
                self._robots[base] = urllib.robotparser.RobotFileParser()   # pas de robots.txt : tout permis
                self._robots[base].parse([])
            else:
                self._robots[base] = None           # injoignable : on s'abstient (non constatable)
        return self._robots[base]

    def autorise(self, url: str) -> Tuple[bool, str]:
        rp = self._regles(url)
        if rp is None:
            return False, "robots_injoignable"
        return (True, "") if rp.can_fetch(self.c.user_agent, url) else (False, "interdit_par_robots")

    def get(self, url: str) -> Reponse:
        ok, raison = self.autorise(url)
        if not ok:
            return Reponse(url, 0, b"", "", raison)
        rep = self._brut(url)
        if rep.statut in (403, 429):                # blocage : on n'insiste pas, on ne contourne pas (DN-10)
            rep.raison = f"bloque_{rep.statut}"
        return rep


def _est_document(url: str, mime: str = "") -> bool:
    chemin = urlparse(url).path.lower()
    return chemin.endswith(EXT_DOCUMENTS) or mime.split(";")[0].strip() in (
        "application/pdf", "application/vnd.oasis.opendocument.text")


def _piste(url: str, texte: str) -> bool:
    if any(m in url.lower() for m in URLS_IGNOREES):
        return False
    s = (url + " " + texte).lower()
    return any(m in s for m in MOTS_PISTES)


class _Suivi(list):
    """Liste d'observations qui prévient un rappel à chaque ajout."""
    def __init__(self, base, rappel):
        super().__init__(base)
        self._rappel = rappel

    def append(self, o):
        super().append(o)
        if self._rappel:
            self._rappel(o)


def parcourir(points_entree: List[str], depot: Depot, config: Optional[Config] = None,
              nav: Optional[Navigateur] = None, maintenant=lambda: datetime.now(timezone.utc)) -> List[Observation]:
    """Un passage de collecte pour une collectivité. Retourne les observations (documents et pages lus)."""
    cfg = config or Config()
    nav = nav or Navigateur(cfg)
    hotes = {urlparse(u).netloc for u in points_entree} | set(cfg.hotes_autorises)
    vu: Set[str] = set()
    file: List[Tuple[str, str, int]] = [(u, "", 0) for u in points_entree]
    obs: List[Observation] = []
    _ajout = obs.append
    obs = _Suivi(obs, cfg.sur_observation)
    pages = 0
    debut = time.monotonic()
    while file and pages < cfg.pages_max:
        if cfg.duree_max and time.monotonic() - debut > cfg.duree_max:
            break
        url, hote_page, prof = file.pop(0)
        if url in vu:
            continue
        vu.add(url)
        if urlparse(url).netloc not in hotes:
            continue
        if cfg.sans_telechargement and _est_document(url) and any(m in url for m in cfg.sans_telechargement):
            obs.append(Observation(url, hote_page, "liste", est_document=True))     # vu dans une liste, non téléchargé
            continue
        rep = nav.get(url)
        if cfg.verbeux:
            print(f"[{len(obs)}] {rep.statut} {url} {rep.raison}", flush=True)
        est_doc = _est_document(rep.url or url, rep.mime)
        if rep.statut != 200:
            obs.append(Observation(url, hote_page, "non_constatable", raison=rep.raison or f"http_{rep.statut}",
                                   est_document=est_doc))
            continue
        h = depot.archiver(rep.url or url, rep.contenu, rep.mime, rep.statut, maintenant())
        obs.append(Observation(url, hote_page, "present", sha256=h, mime=rep.mime, taille=len(rep.contenu),
                               est_document=est_doc))
        if est_doc:
            continue
        pages += 1
        if prof >= cfg.profondeur_max or "html" not in rep.mime.lower():
            continue
        for lien, texte in extraire_liens(rep.contenu.decode("utf-8", "replace"), rep.url or url):
            if lien in vu:
                continue
            if _est_document(lien) or _piste(lien, texte):
                file.append((lien, url, prof + 1))
    return obs


def comparer_passages(avant: List[Observation], apres: List[Observation]) -> Dict[str, str]:
    """État de chaque document vu au passage précédent : 'present', 'disparu' ou 'non_constatable'.
    'disparu' seulement si la page qui le listait a été relue avec succès et ne le liste plus (P54) ;
    sinon on ne sait pas : jamais de « non » sur une simple absence de lecture."""
    present_apres = {o.url for o in apres if o.statut == "present"}
    pages_lues = {o.url for o in apres if o.statut == "present" and not o.est_document}
    etat: Dict[str, str] = {}
    for o in avant:
        if not (o.est_document and o.statut == "present"):
            continue
        if o.url in present_apres:
            etat[o.url] = "present"
        elif o.page_hote and o.page_hote in pages_lues:
            etat[o.url] = "disparu"
        else:
            etat[o.url] = "non_constatable"
    return etat


def decouvrir_wp_media(base: str, termes: List[str], depot: Depot, nav: Navigateur,
                       maintenant=lambda: datetime.now(timezone.utc), pages_max: int = 3,
                       duree_max: float = 0.0, filtre: str = "") -> List[Observation]:
    """Découverte par l'API publique WordPress (/wp-json/wp/v2/media) : donne la liste des fichiers déposés
    ET leur date de dépôt réelle (preuve de publication tardive, V21/V28). Soumis à robots.txt comme le reste ;
    si l'API est fermée ou absente, on n'invente rien : aucune observation."""
    import json as _json
    from urllib.parse import quote as _q
    import re as _re
    motif = _re.compile(filtre, _re.I) if filtre else None
    vus: Set[str] = set()
    obs: List[Observation] = []
    debut = time.monotonic()
    for terme in termes:
        for page in range(1, pages_max + 1):
            if duree_max and time.monotonic() - debut > duree_max:
                return obs
            recherche = f"search={_q(terme)}&" if terme else "orderby=date&order=desc&"
            api = (f"{base.rstrip('/')}/wp-json/wp/v2/media?{recherche}per_page=100&page={page}"
                   "&_fields=id,date,source_url,mime_type")
            rep = nav.get(api)
            if rep.statut != 200:
                # diagnostic : API fermée, bloquée, interdite par robots.txt ou fin de pagination (400 attendu après la dernière page)
                obs.append(Observation(api, "", "non_constatable", raison=(rep.raison or f"http_{rep.statut}") + f"@page{page}"))
                break
            try:
                items = _json.loads(rep.contenu.decode("utf-8", "replace"))
            except ValueError:
                break
            if not isinstance(items, list) or not items:
                if page == 1:
                    obs.append(Observation(api, "", "non_constatable", raison="api_media_vide"))
                break
            for it in items:
                url = it.get("source_url") or ""
                if not url or url in vus or not _est_document(url, it.get("mime_type", "")):
                    continue
                if motif and not motif.search(url):
                    continue
                vus.add(url)
                r = nav.get(url)
                if r.statut != 200:
                    obs.append(Observation(url, api, "non_constatable", raison=r.raison or f"http_{r.statut}",
                                           est_document=True, depose_le_site=it.get("date", "")))
                    continue
                h = depot.archiver(r.url or url, r.contenu, r.mime, r.statut, maintenant())
                obs.append(Observation(url, api, "present", sha256=h, mime=r.mime, taille=len(r.contenu),
                                       est_document=True, depose_le_site=it.get("date", "")))
    return obs
