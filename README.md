# Tandem / Score Citoyen — collecte
Robot de collecte des documents publics des collectivités. Voir config/collectivites.json.

**👉 [Rapport d'avancement du robot (mis à jour toutes les 6 h)](RAPPORT.md)**

## Fonctionnement autonome
- `collecte.yml` : lancé toutes les 6 h (cron) ou à la main. `run_collecte.py --cycle` décide : reprendre un passage interrompu, démarrer un passage (dernier complet > 20 h), ou ne rien faire. Jamais deux passages en parallèle (`concurrency`).
- Progression persistante : `etat/statut.json` + dossier `manifeste/` (un fichier par collectivité et par passage, pour rester loin de la limite de 100 Mo par fichier de GitHub), versionnés dans git par `scripts/sauvegarde.sh` (après chaque collectivité et toutes les 10 min). Le point de reprise est publié depuis une copie de travail temporaire : il ne touche jamais aux fichiers que le robot est en train d'écrire ; un échec de publication est signalé (alerte). L'ancien fichier unique `manifeste.jsonl` est découpé automatiquement, sans perte et avec vérification, par `scripts/decouper_manifeste.py`.
- Contrôle de qualité à la fin de chaque passage : une collectivité dont le nombre d'adresses observées tombe sous la moitié de la médiane des 5 passages précédents (ou à zéro) est signalée « passage incomplet » (alerte et rapport en rouge), même si le passage s'est terminé sans erreur.
- `surveillance.yml` (toutes les 3 h) : ouvre une issue « alerte-robot » si aucun passage complet depuis 36 h, ou passage bloqué depuis 12 h ; relance le robot si besoin ; ferme l'alerte au retour à la normale.
- Limites : GitHub Actions ne garantit pas un processus permanent (lancements planifiés, parfois retardés ; cron désactivé après 60 jours sans activité du dépôt) ; documents archivés conservés 14 jours en artefact seulement.
- `rapport.yml` (toutes les 6 h) : régénère `RAPPORT.md` avec `rapport.py` — état du robot en français simple, sans e-mail ni notification.
