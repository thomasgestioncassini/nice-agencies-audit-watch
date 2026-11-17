"""Surveillance du dépôt public nice-agencies-open-audit, depuis un dépôt séparé.

Chaque jour, ce script lit le dépôt de l'auditeur par l'API publique de GitHub et vérifie :
  S-1  archivage hebdomadaire fait à temps (un relevé de moins de 8 jours) ;
  S-2  tirage au sort présent pour le relevé du lundi, une fois passé le mardi 09:00 UTC ;
  S-3  audit mensuel des deux IA présent, une fois passé le premier mardi du mois 12:00 UTC ;
  S-4  mandat et réglages de l'audit inchangés (empreintes épinglées dans expected.json) ;
  S-5  aucun relevé ni rapport supprimé ou modifié après sa publication (registre state/ledger.json) ;
  S-6  historique du dépôt non réécrit (le dernier commit vu est toujours un ancêtre de la branche) ;
  S-7  dernières exécutions programmées de l'auditeur réussies.
Une anomalie ouvre une alerte publique (issue) dans ce dépôt et fait échouer l'exécution.
Bibliothèque standard seulement. Aucune écriture dans le dépôt surveillé.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

TARGET = 'thomasgestioncassini/nice-agencies-open-audit'
ROOT = Path(__file__).resolve().parent
API = 'https://api.github.com'
START_WEEKLY = dt.date(2026, 11, 23)     # premier lundi d'archivage programmé
START_MONTHLY = dt.date(2026, 12, 1)     # premier audit mensuel programmé
PINNED = ['config/mandate-v1.md', 'config/ai-models.json', 'config/audit-policy.json', 'config/methodology-v5.json',
          'config/networks.json', '.github/workflows/archive.yml', '.github/workflows/audit-ia.yml']


def api(path: str, method: str = 'GET', body: dict | None = None, repo: str = TARGET):
    req = urllib.request.Request(f'{API}/repos/{repo}/{path}', method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header('Accept', 'application/vnd.github+json')
    tok = os.environ.get('GITHUB_TOKEN')
    if tok:
        req.add_unredirected_header('Authorization', f'Bearer {tok}')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b'null')


def tree(sha: str) -> dict:
    return {e['path']: e for e in api(f'git/trees/{sha}')['tree']}


def first_tuesday(y: int, m: int) -> dt.date:
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(1 - d.weekday()) % 7)


def last_monday(today: dt.date) -> dt.date:
    return today - dt.timedelta(days=today.weekday())


def check_schedule(now: dt.datetime, snapshots: dict, reports: list[str], draws: set[str]) -> list[dict]:
    """S-1 à S-3. snapshots : {nom du relevé}, reports : noms des rapports ayant une analyse d'IA, draws : relevés tirés."""
    out, today = [], now.date()
    dates = sorted(n[:10] for n in snapshots)
    if today >= START_WEEKLY + dt.timedelta(days=1):
        if not dates or (today - dt.date.fromisoformat(dates[-1])).days > 8:
            out.append({'code': 'S-1', 'titre': 'Archivage hebdomadaire manquant ou en retard',
                        'detail': f"dernier relevé archivé : {dates[-1] if dates else 'aucun'}"})
        mon = last_monday(today)
        due = dt.datetime.combine(mon + dt.timedelta(days=1), dt.time(9), dt.timezone.utc)
        if mon >= START_WEEKLY and now >= due:
            week = [n for n in snapshots if n[:10] == mon.isoformat()]
            if not week:
                out.append({'code': 'S-1', 'titre': 'Relevé du lundi non archivé', 'detail': f'aucun relevé daté du {mon}'})
            elif not any(n in draws for n in week):
                out.append({'code': 'S-2', 'titre': 'Tirage au sort manquant', 'detail': f'relevé du {mon} sans draw.json'})
    ft = first_tuesday(today.year, today.month)
    if ft >= START_MONTHLY and now >= dt.datetime.combine(ft, dt.time(12), dt.timezone.utc):
        stamp = ft.strftime('%Y%m%d')
        if not any(r.split('_')[-1][:8] >= stamp and r.split('_')[-1][:6] == stamp[:6] for r in reports):
            out.append({'code': 'S-3', 'titre': 'Audit mensuel des deux IA manquant',
                        'detail': f'aucun rapport d’audit IA publié depuis le {ft}'})
    return out


def snap_state(entries: dict) -> dict:
    """État d'un relevé : empreinte de ses fichiers hors tirage, et empreinte du tirage (ajouté plus tard, une seule fois)."""
    files = sorted((p, e['sha']) for p, e in entries.items() if p != 'draw.json')
    return {'contenu': hashlib.sha256(json.dumps(files).encode()).hexdigest(),
            'tirage': (entries.get('draw.json') or {}).get('sha')}


def check_ledger(ledger: dict, current: dict) -> list[dict]:
    """S-5 : chaque dossier déjà vu doit exister, inchangé. Seule évolution admise : l'ajout du tirage à un relevé."""
    out = []
    for name, sha in (ledger.get('reports') or {}).items():
        now = current['reports'].get(name)
        if now is None:
            out.append({'code': 'S-5', 'titre': f'Dossier supprimé : reports/{name}', 'detail': f'empreinte vue : {sha}'})
        elif now != sha:
            out.append({'code': 'S-5', 'titre': f'Dossier modifié après publication : reports/{name}', 'detail': f'{sha} → {now}'})
    for name, old in (ledger.get('snapshots') or {}).items():
        now = current['snapshots'].get(name)
        if now is None:
            out.append({'code': 'S-5', 'titre': f'Dossier supprimé : snapshots/{name}', 'detail': f"empreinte vue : {old['contenu']}"})
        elif now['contenu'] != old['contenu']:
            out.append({'code': 'S-5', 'titre': f'Relevé modifié après publication : snapshots/{name}',
                        'detail': f"{old['contenu']} → {now['contenu']}"})
        elif old.get('tirage') and now.get('tirage') != old['tirage']:
            out.append({'code': 'S-5', 'titre': f'Tirage au sort modifié ou supprimé : snapshots/{name}',
                        'detail': f"{old['tirage']} → {now.get('tirage')}"})
    return out


def check_pins(expected: dict, hashes: dict) -> list[dict]:
    return [{'code': 'S-4', 'titre': f'Fichier de mandat ou de réglage modifié : {p}',
             'detail': f"épinglé {expected.get(p)} ; lu {h}. Si le changement est voulu, publier son motif et mettre "
                       f"à jour expected.json."} for p, h in hashes.items() if expected.get(p) != h]


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    head = api('commits/main')['sha']
    root = tree(api(f'git/commits/{head}')['tree']['sha'])
    snaps = tree(root['snapshots']['sha'])
    reps = tree(root['reports']['sha'])
    ep, lp = ROOT / 'expected.json', ROOT / 'state' / 'ledger.json'
    ledger = json.loads(lp.read_text()) if lp.exists() else {}
    seen = ledger.get('snapshots') or {}
    current = {'snapshots': {}, 'reports': {n: e['sha'] for n, e in reps.items() if e['type'] == 'tree'}}
    for n, e in snaps.items():
        if e['type'] == 'tree':      # arborescence relue seulement si son empreinte a changé depuis le dernier contrôle
            current['snapshots'][n] = ({k: seen[n][k] for k in ('contenu', 'tirage')} if n in seen and seen[n].get('arbre') == e['sha']
                                       else snap_state(tree(e['sha'])))
            current['snapshots'][n]['arbre'] = e['sha']
    draws = {n for n, v in current['snapshots'].items() if v.get('tirage')}
    ai = [n for n in sorted(current['reports'])[-12:] if not n.startswith('canari') and 'agent-a.json' in tree(current['reports'][n])]
    alerts = check_schedule(now, current['snapshots'], ai, draws)

    hashes = {}
    for p in PINNED:
        req = urllib.request.Request(f'https://raw.githubusercontent.com/{TARGET}/{head}/{p}')
        try:
            hashes[p] = hashlib.sha256(urllib.request.urlopen(req, timeout=60).read()).hexdigest()
        except urllib.error.HTTPError as e:
            hashes[p] = f'illisible ({e.code})'
    if '--init' in sys.argv:
        ep.write_text(json.dumps({'note': 'Empreintes SHA-256 épinglées. Toute modification doit être motivée dans CHANGES.md.',
                                  'commit': head, 'files': hashes}, ensure_ascii=False, indent=1) + '\n')
    alerts += check_pins(json.loads(ep.read_text())['files'], hashes)

    alerts += check_ledger(ledger, current)
    if ledger.get('head') and ledger['head'] != head:
        try:
            st = api(f"compare/{ledger['head']}...{head}")['status']
        except urllib.error.HTTPError as e:
            st = f'erreur {e.code}'
        if st not in ('ahead', 'identical'):
            alerts.append({'code': 'S-6', 'titre': 'Historique du dépôt réécrit',
                           'detail': f"le commit {ledger['head']} n'est plus un ancêtre de main ({st})"})
    for wf in ('archive.yml', 'audit-ia.yml'):
        runs = api(f'actions/workflows/{wf}/runs?event=schedule&per_page=1').get('workflow_runs') or []
        if runs and runs[0]['status'] == 'completed' and runs[0]['conclusion'] != 'success':
            alerts.append({'code': 'S-7', 'titre': f'Dernière exécution programmée en échec : {wf}',
                           'detail': f"exécution {runs[0]['id']} du {runs[0]['created_at']} : {runs[0]['conclusion']}"})

    # le registre n'oublie jamais un dossier : les empreintes vues restent, les nouvelles s'ajoutent
    new = {'head': head if not any(a['code'] == 'S-6' for a in alerts) else ledger.get('head'), 'vu_le': now.isoformat(timespec='seconds')}
    new['reports'] = {**current['reports'], **(ledger.get('reports') or {})}
    new['snapshots'] = dict(seen)
    for n, v in current['snapshots'].items():
        old = seen.get(n)
        if old is None or (v['contenu'] == old['contenu'] and (not old.get('tirage') or v.get('tirage') == old['tirage'])):
            new['snapshots'][n] = v      # nouveau relevé, ou relevé inchangé (tirage éventuellement ajouté)
    lp.parent.mkdir(exist_ok=True)
    lp.write_text(json.dumps(new, ensure_ascii=False, indent=1, sort_keys=True) + '\n')

    lines = [f"# Surveillance du {now:%Y-%m-%d %H:%M} UTC", '', f"Dépôt surveillé : {TARGET}, commit {head[:8]}.",
             f"{len(current['snapshots'])} relevés et {len(current['reports'])} rapports suivis.", '']
    lines += [f"- **{a['code']}** · {a['titre']} — {a['detail']}" for a in alerts] or ['Aucune anomalie.']
    (ROOT / 'state' / 'dernier-controle.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    if alerts and os.environ.get('GITHUB_REPOSITORY') and os.environ.get('GITHUB_TOKEN'):
        me = os.environ['GITHUB_REPOSITORY']
        open_ = {i['title'] for i in api('issues?state=open&per_page=100', repo=me)}
        for a in alerts:
            t = f"[{a['code']}] {a['titre']}"
            if t not in open_:
                api('issues', 'POST', {'title': t, 'body': f"{a['detail']}\n\nContrôle du {now:%Y-%m-%d %H:%M} UTC, commit surveillé {head}."}, repo=me)
    return 1 if alerts else 0


if __name__ == '__main__':
    sys.exit(main())
