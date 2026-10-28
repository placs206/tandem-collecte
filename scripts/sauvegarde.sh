#!/usr/bin/env bash
# Point de reprise : versionne le manifeste et l'état dans git (stockage persistant gratuit). Best-effort : n'échoue jamais.
set -u
git config user.name collecte-bot
git config user.email collecte-bot@users.noreply.github.com
git add manifeste.jsonl etat/statut.json 2>/dev/null
git commit -qm "point de reprise $(date -u +%FT%TZ)" 2>/dev/null || exit 0
for essai in 1 2 3; do
  git pull -q --rebase -X theirs origin main && git push -q origin HEAD:main && exit 0
  git rebase --abort 2>/dev/null
  sleep $((essai * 5))
done
echo "ALERTE : push du point de reprise impossible (sera retenté au prochain point)" >&2
exit 0
