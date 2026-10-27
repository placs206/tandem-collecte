"""Passe 2 d'extraction : lecture par une IA (spécification 3.2, DN-14). Aucun appel réseau dans ce module :
le client est injecté (`Client.completer(consigne) -> str`), ce qui rend la passe testable et le modèle remplaçable
(le choix du modèle reste en attente, architecture-technique.md section 11).

Garde-fous :
- la consigne ne mentionne JAMAIS de note, de conclusion attendue ni d'obligation à satisfaire (pas d'influence) ;
- la réponse est du JSON strict ; tout fait dont la citation n'est pas retrouvée mot pour mot dans le document est rejeté ;
- l'IA ne produit jamais un résultat d'obligation (oui/non) : seulement des faits sourcés ;
- sont « douteux » (à relire) : confiance < 0,8, citation introuvable, contradiction avec la passe 1, réponse illisible,
  et toute ABSENCE affirmée par l'IA (une absence ne se prouve pas par une citation : un humain la confirme avant « non »).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from constats import Fait
from typage import normaliser

VERSION_CONSIGNE = "consigne-ia-0.1"
SEUIL_CONFIANCE = 0.8

QUESTIONS = {   # clé du fait -> question posée (formulée sans suggérer de réponse)
    "seance_date": "Quelle est la date de la séance ? (format AAAA-MM-JJ)",
    "heure": "À quelle heure la séance a-t-elle commencé ?",
    "president": "Qui présidait la séance ?",
    "presents": "Le document indique-t-il les membres présents ou représentés ?",
    "secretaire": "Le document désigne-t-il un ou plusieurs secrétaires de séance ?",
    "quorum": "Le document mentionne-t-il que le quorum est atteint ou constaté ?",
    "ordre_du_jour": "Le document reprend-il l'ordre du jour ?",
    "deliberations_adoptees": "Le document indique-t-il les délibérations adoptées ?",
    "rapports_cites": "Le document cite-t-il les rapports au vu desquels les délibérations sont adoptées ?",
    "scrutin_particulier_demande": "Une demande de scrutin public ou secret est-elle mentionnée ? "
                                    "Répondre « aucune_demande » si le document dit qu'il n'y en a pas eu.",
    "resultat_scrutins": "Le résultat des votes (pour, contre, abstentions) est-il indiqué ?",
    "teneur_discussions": "Le document rend-il compte de la teneur des discussions ?",
    "signature_ou_mention_signe": "Le document porte-t-il une signature ou la mention « signé » ?",
}


@dataclass
class Resultat:
    faits: Dict[str, Fait] = field(default_factory=dict)
    douteux: List[dict] = field(default_factory=list)
    jetons: int = 0


class Client(Protocol):
    def completer(self, consigne: str) -> str: ...


def construire_consigne(texte: str, cles: List[str]) -> str:
    q = "\n".join(f'- "{k}" : {QUESTIONS[k]}' for k in cles)
    return (
        "Tu lis un document d'une collectivité française. Réponds uniquement par un objet JSON.\n"
        "Pour chaque question ci-dessous, donne : \"valeur\" (true, false, null, ou la valeur demandée), "
        "\"extrait\" (citation EXACTE, mot pour mot, copiée du document ; vide si valeur false ou null), "
        "\"page\" (entier ou null), \"confiance\" (nombre entre 0 et 1), \"raison_du_doute\" (texte ou null).\n"
        "Ne devine rien : si le document ne permet pas de répondre, mets null.\n\n"
        f"Questions :\n{q}\n\nDocument :\n\"\"\"\n{texte}\n\"\"\"\n"
        f"[{VERSION_CONSIGNE}]"
    )


def _extraire_json(brut: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", brut, flags=re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return d if isinstance(d, dict) else None
    except json.JSONDecodeError:
        return None


def lire(texte: str, cles: List[str], client: Client, passe1: Optional[Dict[str, Fait]] = None) -> Resultat:
    """Interroge l'IA sur les faits non tranchés par la passe 1 et valide la réponse."""
    res = Resultat()
    brut = client.completer(construire_consigne(texte, cles))
    d = _extraire_json(brut)
    if d is None:
        res.douteux = [{"fait": k, "motif": "réponse illisible"} for k in cles]
        res.faits = {k: Fait(k, None, douteux=True) for k in cles}
        return res
    t_norm = normaliser(texte)
    for k in cles:
        r = d.get(k)
        if not isinstance(r, dict):
            res.faits[k] = Fait(k, None, douteux=True)
            res.douteux.append({"fait": k, "motif": "fait absent de la réponse"})
            continue
        valeur, extrait = r.get("valeur"), (r.get("extrait") or "").strip()
        try:
            conf = float(r.get("confiance", 0))
        except (TypeError, ValueError):
            conf = 0.0
        f = Fait(k, valeur)
        f.detail = extrait          # type: ignore[attr-defined]
        f.confiance = conf          # type: ignore[attr-defined]
        motifs = []
        if valeur not in (None, False) and not extrait:
            motifs.append("aucune citation fournie")
        elif extrait and normaliser(extrait) not in t_norm:
            motifs.append("citation introuvable dans le document")     # fait rejeté : valeur neutralisée
            f.valeur = None
        if valeur is False:
            # Une absence affirmée ne peut pas être prouvée par une citation : elle est confirmée par un humain
            # avant de compter « non » (DN-48). Tant que non confirmée : « à vérifier ».
            motifs.append("absence affirmée par l'IA : à confirmer par un relecteur")
        if conf < SEUIL_CONFIANCE:
            motifs.append(f"confiance {conf:.2f} < {SEUIL_CONFIANCE}")
        if passe1 and k in passe1 and passe1[k].valeur is not None and valeur is not None \
                and passe1[k].valeur != valeur:
            motifs.append("contradiction avec la passe 1")
        if r.get("raison_du_doute"):
            motifs.append(f"doute signalé : {r['raison_du_doute']}")
        if motifs:
            f.douteux = True
            res.douteux.append({"fait": k, "motif": "; ".join(motifs)})
        res.faits[k] = f
    return res


def fusionner(passe1: Dict[str, Fait], ia: Resultat) -> Dict[str, Fait]:
    """Passe 1 prime quand elle a trouvé (formule sans ambiguïté) ; l'IA complète le reste."""
    out = dict(passe1)
    for k, f in ia.faits.items():
        if k not in out or out[k].valeur is None:
            out[k] = f
    return out


def lire_double(texte: str, cles: List[str], client_a: Client, client_b: Client,
                passe1: Optional[Dict[str, Fait]] = None) -> Resultat:
    """Double lecture par DEUX modèles différents (ex. ChatGPT et Claude). Un désaccord sur un fait le rend
    douteux (relecture humaine) : deux avis indépendants qui concordent valent plus qu'un seul (rigueur
    scientifique, DN-51). Le fait retenu est celui du modèle A ; le doute, lui, vient du désaccord."""
    a = lire(texte, cles, client_a, passe1)
    b = lire(texte, cles, client_b, passe1)
    out = Resultat(faits=dict(a.faits), douteux=list(a.douteux), jetons=a.jetons + b.jetons)
    deja = {d["fait"] for d in out.douteux}
    for k in cles:
        fa, fb = a.faits[k], b.faits[k]
        if fa.valeur != fb.valeur:
            fa.douteux = True
            if k not in deja:
                out.douteux.append({"fait": k, "motif": f"désaccord entre les deux modèles ({fa.valeur} / {fb.valeur})"})
            else:
                for d in out.douteux:
                    if d["fait"] == k:
                        d["motif"] += f"; désaccord entre les deux modèles ({fa.valeur} / {fb.valeur})"
        elif fb.douteux and k not in deja:
            fa.douteux = True
            out.douteux.append({"fait": k, "motif": "doute du second modèle: " +
                                next(d["motif"] for d in b.douteux if d["fait"] == k)})
    return out
