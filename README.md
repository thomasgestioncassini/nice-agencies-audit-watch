# nice-agencies-audit-watch

Surveillance quotidienne du dépôt public [nice-agencies-open-audit](https://github.com/thomasgestioncassini/nice-agencies-open-audit),
l'auditeur du classement meilleure-agence-nice.fr. Ce dépôt est séparé de l'auditeur : il ne fait que le lire.

## Ce qui est vérifié chaque jour

| Code | Contrôle |
| --- | --- |
| S-1 | Un relevé est archivé chaque lundi (depuis le 23/11/2026) |
| S-2 | Le tirage au sort du relevé du lundi existe le mardi à 09:00 UTC |
| S-3 | L'audit mensuel des deux IA est publié le premier mardi du mois à 12:00 UTC (depuis décembre 2026) |
| S-4 | Le mandat des IA, les modèles, la politique d'audit, la méthode suivie et les deux programmes d'exécution sont inchangés (empreintes dans `expected.json`) |
| S-5 | Aucun relevé ni rapport n'est supprimé ou modifié après publication (`state/ledger.json`). Seul ajout admis : le tirage d'un relevé, une seule fois |
| S-6 | L'historique du dépôt n'est pas réécrit |
| S-7 | Les dernières exécutions programmées de l'auditeur ont réussi |

Une anomalie ouvre une alerte publique (onglet Issues) et fait échouer l'exécution. Le dernier contrôle est dans
`state/dernier-controle.md`. Un changement voulu d'un fichier épinglé se fait en mettant à jour `expected.json`, avec son
motif dans `CHANGES.md`.

## Limites

- Ce dépôt appartient au même compte GitHub que l'auditeur et que le site audité : SARL GESTION CASSINI, éditrice du
  classement et exploitante de deux agences classées. La surveillance est séparée de l'auditeur, **pas indépendante de
  l'éditeur**, qui peut modifier ou arrêter ce dépôt. Toute personne peut en faire une copie et la faire tourner.
- Le registre ne connaît que ce qui existait au premier contrôle (17/11/2026) et après.
- La surveillance constate ; elle ne répare rien et ne juge pas le contenu des rapports.

## Lancer soi-même

```
python3 -m unittest
python3 watch.py        # bibliothèque standard seulement ; GITHUB_TOKEN facultatif
```
