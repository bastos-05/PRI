"""Wikidata metadata with Wikipedia infobox fallback; keep raw.jsonl intact."""
import json
import os
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import mwparserfromhell
import requests

DATA_PATH = Path('/opt/airflow/data' if os.path.exists('/opt/airflow') else '/app/data')
WP_API = 'https://en.wikipedia.org/w/api.php'
WD_API = 'https://www.wikidata.org/w/api.php'
PROPERTIES = {
    'location': ('P276', 'P131', 'P17'), 'coordinates': ('P625',),
    'date': ('P585',), 'start_date': ('P580',), 'end_date': ('P582',),
    'deaths': ('P1120',), 'injured': ('P1339',), 'damages': ('P2630',),
}
INFOBOX = {
    'location': ('location', 'site', 'place', 'country'),
    'date': ('date', 'occurrence date'), 'start_date': ('start date',),
    'end_date': ('end date',), 'deaths': ('fatalities', 'deaths', 'total fatalities'),
    'injured': ('injuries', 'injured', 'total injuries'), 'missing': ('missing',),
    'casualties': ('casualties',),
    'damages': ('damages', 'damage', 'property damage', 'economic losses'),
}


class Client:
    def __init__(self, path, refresh=False):
        self.cache = sqlite3.connect(path)
        self.cache.execute('CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, body TEXT)')
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'PRIResearchCrawler/1.0 (contact:up202207447@up.pt)'
        self.refresh = refresh
        self.last_request = 0.0

    def close(self):
        self.session.close()
        self.cache.close()

    def get(self, url, params):
        key = json.dumps([url, params], sort_keys=True)
        cached = self.cache.execute('SELECT body FROM responses WHERE key = ?', (key,)).fetchone()
        if cached and not self.refresh:
            return json.loads(cached[0])
        for attempt in range(5):
            time.sleep(max(0, .35 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.session.get(url, params={**params, 'format': 'json', 'maxlag': 5}, timeout=60)
                if response.status_code in (429, 503):
                    time.sleep(max(5, float(response.headers.get('Retry-After', 2 ** attempt))))
                    continue
                response.raise_for_status()
                data = response.json()
                if data.get('error', {}).get('code') == 'maxlag':
                    time.sleep(max(5, 2 ** attempt))
                    continue
                if 'error' in data:
                    raise RuntimeError(data['error'])
                data['_retrieved_at'] = datetime.now(timezone.utc).isoformat()
                with self.cache:
                    self.cache.execute('INSERT OR REPLACE INTO responses VALUES (?, ?)', (key, json.dumps(data)))
                return data
            except (requests.RequestException, ValueError):
                if attempt == 4:
                    raise
                time.sleep(max(5, 2 ** attempt))
        raise RuntimeError('Wikimedia retries exhausted')

    def entities(self, ids, props='claims|labels'):
        ids = sorted(set(ids))
        result = {}
        for offset in range(0, len(ids), 50):
            data = self.get(WD_API, {'action': 'wbgetentities', 'ids': '|'.join(ids[offset:offset + 50]),
                                     'props': props, 'languages': 'en|pt'})
            for entity_id, entity in data['entities'].items():
                entity['retrieved_at'] = data['_retrieved_at']
                result[entity_id] = entity
        return result

    def page_items(self, articles):
        ids = [str(a['page_id']) for a in articles if 'wikidata_id' not in a]
        if not ids:
            return {}
        data = self.get(WP_API, {'action': 'query', 'prop': 'pageprops', 'ppprop': 'wikibase_item',
                                'pageids': '|'.join(ids), 'formatversion': 2})
        return {p['pageid']: p.get('pageprops', {}).get('wikibase_item') for p in data['query']['pages']}


def statements(entity, prop):
    claims = [c for c in entity.get('claims', {}).get(prop, []) if c.get('rank') != 'deprecated']
    return [c for c in claims if c.get('rank') == 'preferred'] or claims


def infobox_metadata(wikitext):
    result = {}
    for template in mwparserfromhell.parse(wikitext).filter_templates():
        name = str(template.name).strip().lower().replace('_', ' ')
        if not name.startswith('infobox'):
            continue
        for param in template.params:
            key = re.sub(r'\s+', ' ', str(param.name).strip().lower().replace('_', ' '))
            for field, aliases in INFOBOX.items():
                if key not in aliases:
                    continue
                raw = str(param.value).strip()
                parsed = mwparserfromhell.parse(raw)
                for tag in list(parsed.filter_tags()):
                    if str(tag.tag).strip().lower() == 'ref':
                        parsed.remove(tag)
                text = parsed.strip_code(keep_template_params=True).strip()
                if not text or text.lower() in ('unknown', 'n/a', 'not known', '–', '—', '?'):
                    continue
                result.setdefault(field, []).append({'source': 'wikipedia_infobox', 'template': name,
                                                      'parameter': key, 'text': text, 'raw': raw})
    return result


def build_metadata(article, entity, labels):
    metadata = {field: None for field in (*PROPERTIES, 'missing', 'casualties')}
    fallback = infobox_metadata(article.get('wikitext', ''))
    for field, props in PROPERTIES.items():
        # P580/P582 on a structure may describe construction/closure, not a disaster.
        if field in ('start_date', 'end_date') and not (fallback.get('date') or entity.get('claims', {}).get('P585')):
            continue
        for prop in props:
            values = []
            for claim in statements(entity, prop):
                snak = claim.get('mainsnak', {})
                value = snak.get('datavalue', {}).get('value')
                if snak.get('snaktype') != 'value' or value is None:
                    continue
                entry = {'source': 'wikidata', 'property': prop, 'value': value,
                         'statement_id': claim.get('id'), 'rank': claim.get('rank', 'normal'),
                         'qualifiers': claim.get('qualifiers', {}), 'references': claim.get('references', []),
                         'retrieved_at': entity.get('retrieved_at')}
                if isinstance(value, dict) and value.get('id'):
                    entry['label'] = labels.get(value['id'], value['id'])
                values.append(entry)
            if values:
                metadata[field] = values
                break
    for field, values in fallback.items():
        if metadata[field] is None:
            for value in values:
                value['revision_id'] = article.get('revision_id')
            metadata[field] = values
    return metadata


def enrich_batch(articles, client):
    page_items = client.page_items(articles)
    for article in articles:
        if 'wikidata_id' not in article:
            article['wikidata_id'] = page_items.get(article['page_id'])
    entities = client.entities([a['wikidata_id'] for a in articles if a.get('wikidata_id')])
    location_ids = set()
    for entity in entities.values():
        for prop in PROPERTIES['location']:
            for claim in statements(entity, prop):
                value = claim.get('mainsnak', {}).get('datavalue', {}).get('value', {})
                if isinstance(value, dict) and value.get('id'):
                    location_ids.add(value['id'])
    labels = {qid: (e.get('labels', {}).get('en') or e.get('labels', {}).get('pt') or {}).get('value', qid)
              for qid, e in client.entities(location_ids, 'labels').items()}
    for article in articles:
        article['metadata'] = build_metadata(article, entities.get(article.get('wikidata_id'), {}), labels)
    return articles


def enrich(data_path=DATA_PATH):
    data_path = Path(data_path)
    config = json.loads(os.environ.get('PIPELINE_CONFIG') or '{}').get('metadata') or {}
    client = Client(data_path / 'metadata_cache.db', refresh=config.get('refresh', False))
    temporary = data_path / 'enriched.jsonl.tmp'
    coverage = Counter()
    count = 0
    try:
        with (data_path / 'raw.jsonl').open(encoding='utf-8') as source, temporary.open('w', encoding='utf-8') as dest:
            batch = []

            def write_batch():
                nonlocal count
                for article in enrich_batch(batch, client):
                    dest.write(json.dumps(article, ensure_ascii=False) + '\n')
                    count += 1
                    coverage.update(k for k, v in article['metadata'].items() if v is not None)
                print(f'[METADATA] {count} articles | coverage: {dict(coverage)}', flush=True)

            for line in source:
                if not line.strip():
                    continue
                article = json.loads(line)
                if article.get('page_id') is None:
                    continue
                batch.append(article)
                if len(batch) == 50:
                    write_batch()
                    batch = []
            if batch:
                write_batch()
            dest.flush()
            os.fsync(dest.fileno())
        temporary.replace(data_path / 'enriched.jsonl')
    finally:
        client.close()


if __name__ == '__main__':
    enrich()
