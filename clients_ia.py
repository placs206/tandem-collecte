"""Clients pour la passe 2 (lecture par IA). Trois façons de brancher un modèle sur `extraction_ia.lire`,
sans changer le reste du code (DN-49, DN-50) :

1. ClientManuel : la consigne est écrite dans un fichier ; un humain (ou un assistant) la passe à n'importe quel
   modèle (ChatGPT, Claude…) et dépose la réponse JSON dans le fichier voisin. Aucune clé, aucun réseau.
   Adapté au jeu d'or (20 séances) et à un premier test.
2. ClientOpenAI : appel automatique de l'API d'OpenAI. Une clé d'API est nécessaire (distincte de l'abonnement
   ChatGPT) et un accès réseau sortant : à lancer depuis la machine du développeur.
3. ClientAnthropic : idem avec l'API d'Anthropic.

Les clés se lisent dans l'environnement (OPENAI_API_KEY, ANTHROPIC_API_KEY), jamais dans le code ni dans le projet.
Les noms de modèles ne sont pas figés ici : ils se donnent en paramètre ou par variable d'environnement.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from typing import Optional


class AttenteReponse(Exception):
    """Levée par ClientManuel : une consigne attend sa réponse (le fichier a été écrit)."""

    def __init__(self, cle: str, fichier_consigne: str, fichier_reponse: str):
        super().__init__(f"réponse attendue : {fichier_reponse}")
        self.cle, self.fichier_consigne, self.fichier_reponse = cle, fichier_consigne, fichier_reponse


class ClientManuel:
    def __init__(self, dossier: str):
        self.dossier = dossier
        os.makedirs(dossier, exist_ok=True)

    def completer(self, consigne: str) -> str:
        cle = hashlib.sha256(consigne.encode("utf-8")).hexdigest()[:16]
        f_consigne = os.path.join(self.dossier, f"{cle}.consigne.txt")
        f_reponse = os.path.join(self.dossier, f"{cle}.reponse.json")
        if os.path.exists(f_reponse):
            with open(f_reponse, encoding="utf-8") as f:
                return f.read()
        if not os.path.exists(f_consigne):
            with open(f_consigne, "w", encoding="utf-8") as f:
                f.write(consigne)
        raise AttenteReponse(cle, f_consigne, f_reponse)


def _post(url: str, entetes: dict, corps: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(corps).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **entetes}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class ClientOpenAI:
    def __init__(self, modele: Optional[str] = None, api_key: Optional[str] = None,
                 base_url: str = "https://api.openai.com/v1", timeout: float = 120.0):
        self.modele = modele or os.environ.get("TANDEM_MODELE_OPENAI")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.modele:
            raise ValueError("modèle non précisé (paramètre ou variable TANDEM_MODELE_OPENAI)")
        if not self.api_key:
            raise ValueError("clé d'API absente (variable OPENAI_API_KEY)")
        self.base_url, self.timeout = base_url.rstrip("/"), timeout
        self.jetons_entree = self.jetons_sortie = 0

    def completer(self, consigne: str) -> str:
        d = _post(f"{self.base_url}/chat/completions", {"Authorization": f"Bearer {self.api_key}"},
                  {"model": self.modele, "temperature": 0,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": consigne}]}, self.timeout)
        u = d.get("usage", {})
        self.jetons_entree += u.get("prompt_tokens", 0)
        self.jetons_sortie += u.get("completion_tokens", 0)
        return d["choices"][0]["message"]["content"]


class ClientAnthropic:
    def __init__(self, modele: Optional[str] = None, api_key: Optional[str] = None,
                 base_url: str = "https://api.anthropic.com/v1", timeout: float = 120.0, max_tokens: int = 4096):
        self.modele = modele or os.environ.get("TANDEM_MODELE_ANTHROPIC")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.modele:
            raise ValueError("modèle non précisé (paramètre ou variable TANDEM_MODELE_ANTHROPIC)")
        if not self.api_key:
            raise ValueError("clé d'API absente (variable ANTHROPIC_API_KEY)")
        self.base_url, self.timeout, self.max_tokens = base_url.rstrip("/"), timeout, max_tokens
        self.jetons_entree = self.jetons_sortie = 0

    def completer(self, consigne: str) -> str:
        d = _post(f"{self.base_url}/messages",
                  {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                  {"model": self.modele, "max_tokens": self.max_tokens, "temperature": 0,
                   "messages": [{"role": "user", "content": consigne}]}, self.timeout)
        u = d.get("usage", {})
        self.jetons_entree += u.get("input_tokens", 0)
        self.jetons_sortie += u.get("output_tokens", 0)
        return "".join(b.get("text", "") for b in d.get("content", []))
