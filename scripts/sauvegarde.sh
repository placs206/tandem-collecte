#!/usr/bin/env bash
# Point de reprise : publie l'état (etat/statut.json) et le manifeste (dossier manifeste/, ou ancien manifeste.jsonl)
# sur main SANS toucher au répertoire de travail du robot.
# Les fichiers sont copiés dans une copie de travail temporaire (git worktree) partie de la dernière version de main,
# puis commités et poussés depuis cette copie. Le robot peut continuer à écrire pendant ce temps.
# (Anomalie A-01 de l'audit du 28/10/2026 : l'ancien « git pull --rebase » remplaçait le fichier ouvert par le robot,
#  et toutes les observations écrites ensuite étaient perdues sans erreur.)
# Les fichiers du robot priment toujours sur ceux de main ; les autres fichiers de main (code, rapport) sont conservés.
# Si l'ancien manifeste.jsonl a été découpé (scripts/decouper_manifeste.py), sa suppression est publiée aussi.
# Code de sortie : 0 = publié ou rien de nouveau ; 1 = échec après 3 essais (visible : alerte).
set -u
racine=$(git rev-parse --show-toplevel) || exit 1
cd "$racine" || exit 1
tmp=$(mktemp -d)
wt="$tmp/wt"
nettoyer() { git worktree remove --force "$wt" >/dev/null 2>&1; rm -rf "$tmp"; git worktree prune >/dev/null 2>&1; }
trap nettoyer EXIT
for essai in 1 2 3; do
  git worktree remove --force "$wt" >/dev/null 2>&1; rm -rf "$wt"; git worktree prune >/dev/null 2>&1
  if git fetch -q --depth=1 origin main && git worktree add -q --detach "$wt" FETCH_HEAD; then
    mkdir -p "$wt/etat"
    [ -f etat/statut.json ] && cp etat/statut.json "$wt/etat/statut.json"
    if [ -d manifeste ]; then
      mkdir -p "$wt/manifeste"
      cp -R manifeste/. "$wt/manifeste/"
    fi
    if [ -f manifeste.jsonl ]; then
      cp manifeste.jsonl "$wt/manifeste.jsonl"
    elif [ -d manifeste ]; then
      git -C "$wt" rm -q --ignore-unmatch manifeste.jsonl   # ancien fichier découpé : sa suppression est publiée
    fi
    git -C "$wt" add -A -- etat
    [ -d "$wt/manifeste" ] && git -C "$wt" add -A -- manifeste
    [ -f "$wt/manifeste.jsonl" ] && git -C "$wt" add -- manifeste.jsonl
    git -C "$wt" diff --cached --quiet && exit 0            # rien de nouveau depuis le dernier point de reprise
    if git -C "$wt" -c user.name=collecte-bot -c user.email=collecte-bot@users.noreply.github.com \
         commit -qm "point de reprise $(date -u +%FT%TZ)" && git -C "$wt" push -q origin HEAD:main; then
      exit 0
    fi
  fi
  echo "point de reprise : essai $essai échoué, nouvel essai" >&2
  sleep $((essai * 5))
done
echo "ALERTE : push du point de reprise impossible après 3 essais" >&2
exit 1
