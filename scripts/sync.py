"""Fetch xAPI statements securely and publish a minimal, actor-free dashboard dataset."""
import base64
import datetime as dt
import json
import os
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

BASE = 'https://shaabanahmed.com/xapi/spanish-learning/'
OLD = 'https://example.org/spanish-learning/xapi/'
ENDPOINT = os.environ['LRS_ENDPOINT'].rstrip('/') + '/'
KEY = os.environ['LRS_KEY']
SECRET = os.environ['LRS_SECRET']
EMAIL = os.environ.get('LEARNER_EMAIL', '').strip().lower()
if urlsplit(ENDPOINT).scheme != 'https' or not ENDPOINT.rstrip('/').endswith('/xapi'):
    raise ValueError('LRS_ENDPOINT must be an HTTPS endpoint ending in /xapi/')
HOST = urlsplit(ENDPOINT).netloc
AUTH = base64.b64encode(f'{KEY}:{SECRET}'.encode()).decode()
HEADERS = {'Authorization': f'Basic {AUTH}', 'X-Experience-API-Version': '1.0.3', 'Accept': 'application/json'}


def permitted_extensions(obj, names):
    result = {}
    for name in names:
        for base in (BASE, OLD):
            k = base + 'extensions/' + name
            if k in (obj or {}):
                result[k] = obj[k]
    return result


def public_statement(s):
    vid = s.get('verb', {}).get('id', '')
    obj = s.get('object', {})
    oid = obj.get('id', '')
    result = s.get('result', {})
    ctx = s.get('context', {})
    if vid.endswith('/studied'):
        return {'verb': {'id': vid}, 'object': {'id': oid, 'definition': {'name': {'en-US': obj.get('definition', {}).get('name', {}).get('en-US', '')}}},
                'result': {'duration': result.get('duration'), 'extensions': permitted_extensions(result.get('extensions'), ('resource', 'primary-format'))},
                'timestamp': s.get('timestamp'), 'stored': s.get('stored')}
    if vid.endswith('/was-assessed'):
        return {'verb': {'id': vid}, 'object': {'id': oid, 'definition': {'name': {'en-US': obj.get('definition', {}).get('name', {}).get('en-US', '')}}},
                'result': {'score': result.get('score', {})},
                'context': {'registration': ctx.get('registration'), 'extensions': permitted_extensions(ctx.get('extensions'), ('cefr-target', 'cefr-assessed', 'assessment-source'))},
                'timestamp': s.get('timestamp'), 'stored': s.get('stored')}
    if vid == BASE + 'verbs/recorded' and oid in (BASE+'activities/anki/cognates', BASE+'activities/anki/phrases'):
        return {'verb': {'id': vid}, 'object': {'id': oid}, 'result': {'extensions': permitted_extensions(result.get('extensions'), ('total-cards', 'mature-cards'))},
                'timestamp': s.get('timestamp'), 'stored': s.get('stored')}
    return None


def main():
    url = urljoin(ENDPOINT, 'statements')
    visited = set()
    all_statements = []
    for _ in range(100):
        if url in visited:
            raise RuntimeError('Repeated pagination URL')
        visited.add(url)
        if urlsplit(url).scheme != 'https' or urlsplit(url).netloc != HOST:
            raise RuntimeError('Pagination URL is outside the LRS host')
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=40) as response:
            body = json.load(response)
        if not isinstance(body.get('statements'), list):
            raise RuntimeError('Unexpected LRS response')
        all_statements.extend(body['statements'])
        if not body.get('more'):
            break
        url = urljoin(url, body['more'])
    else:
        raise RuntimeError('LRS pagination exceeded 100 pages')
    selected = []
    for s in all_statements:
        if EMAIL and s.get('actor', {}).get('mbox', '').lower() != 'mailto:' + EMAIL:
            continue
        item = public_statement(s)
        if item:
            selected.append(item)
    output = {'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'statements': selected}
    Path('data.json').write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':'))+'\n')
    print(f'Published {len(selected)} dashboard statements (from {len(all_statements)} retrieved).')


if __name__ == '__main__':
    main()
