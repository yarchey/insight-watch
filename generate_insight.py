#!/usr/bin/env python3
"""Generate and archive a Complicated-compatible INSIGHT using Gemini."""
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time
import socket
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
LATEST = ROOT / 'latest.json'
ARCHIVE = ROOT / 'archive'
API = 'https://generativelanguage.googleapis.com/v1beta'
REQUIRED = ('title', 'line1', 'line2', 'paradox', 'evidence', 'application', 'experiment', 'topic')
PREFERRED = ('gemini-3.5-flash-lite', 'gemini-3-flash-preview', 'gemini-3.5-flash', 'gemini-2.5-flash-lite')
REQUEST_TIMEOUT = 35
MAX_ATTEMPTS_PER_MODEL = 2


def api_request(path, key, payload=None, timeout=REQUEST_TIMEOUT):
    headers = {'x-goog-api-key': key, 'Accept': 'application/json'}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(API + path, data=data, headers=headers,
                                     method='POST' if data is not None else 'GET')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode('utf-8', errors='replace')[:1500]
        raise RuntimeError(f'Gemini API HTTP {exc.code}: {details}') from exc


def available_models(key):
    models, token = {}, None
    while True:
        suffix = '?pageSize=100'
        if token:
            suffix += '&pageToken=' + urllib.parse.quote(token, safe='')
        page = api_request('/models' + suffix, key)
        for model in page.get('models', []):
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                models[model['name'].split('/')[-1]] = model['name']
        token = page.get('nextPageToken')
        if not token:
            return models


def model_candidates(key):
    configured = os.getenv('GEMINI_MODEL', '').strip().split('/')[-1]
    models = available_models(key)
    if configured:
        if configured not in models:
            raise RuntimeError(f'Configured model {configured} not listed. Available: {", ".join(sorted(models))}')
        return [models[configured]]
    selected = [models[name] for name in PREFERRED if name in models]
    selected += [full for name, full in sorted(models.items())
                 if name not in PREFERRED and 'flash' in name and 'preview' not in name]
    if not selected:
        raise RuntimeError('No suitable Flash model listed: ' + ', '.join(sorted(models)))
    return selected


def generate(history):
    key = os.environ['GEMINI_API_KEY'].strip()
    if not key:
        raise RuntimeError('GEMINI_API_KEY is empty')
    now = dt.datetime.now(ZoneInfo('Europe/Moscow'))
    recent = [item.get('title', '') for item in history[-30:]]
    topics = ('ÑÐºÐ¾Ð½Ð¾Ð¼Ð¸ÐºÐ°', 'ÑÐµÐ¾ÑÐ¸Ñ Ð¸Ð³Ñ', 'Ð¿ÑÐ¸ÑÐ¾Ð»Ð¾Ð³Ð¸Ñ', 'ÑÐ¸Ð·Ð¸ÐºÐ° Ð¸ ÐºÐ¾ÑÐ¼Ð¾Ñ',
              'Ð¸ÑÐºÑÑÑÑÐ²ÐµÐ½Ð½ÑÐ¹ Ð¸Ð½ÑÐµÐ»Ð»ÐµÐºÑ', 'ÑÐ»Ð¾Ð¶Ð½ÑÐµ ÑÐ¸ÑÑÐµÐ¼Ñ')
    topic = topics[len(history) % len(topics)]
    prompt = f'''Ð¢Ñ ÑÐµÐ´Ð°ÐºÑÐ¾Ñ INSIGHT â Ð¸Ð½ÑÐµÐ»Ð»ÐµÐºÑÑÐ°Ð»ÑÐ½ÑÑ Ð¼Ð¸ÐºÑÐ¾ÑÑÑÐµ Ð´Ð»Ñ Apple Watch. Ð¡ÐµÐ¹ÑÐ°Ñ {now:%Y-%m-%d %H:%M} Ð¿Ð¾ ÐÐ¾ÑÐºÐ²Ðµ.
Ð¢ÐµÐ¼Ð° ÑÑÐ¾Ð³Ð¾ Ð²ÑÐ¿ÑÑÐºÐ°: {topic}. Ð¡Ð¾Ð·Ð´Ð°Ð¹ ÐÐÐÐ£ Ð½ÐµÐ¾Ð¶Ð¸Ð´Ð°Ð½Ð½ÑÑ, Ð¸Ð½ÑÐµÐ»Ð»ÐµÐºÑÑÐ°Ð»ÑÐ½Ð¾ ÑÐµÑÑÐ½ÑÑ Ð¸Ð´ÐµÑ Ð½Ð° ÑÑÑÑÐºÐ¾Ð¼. ÐÐ·Ð±ÐµÐ³Ð°Ð¹ Ð±Ð°Ð½Ð°Ð»ÑÐ½ÑÑ ÑÐ¸ÑÐ°Ñ, Ð¼Ð¸ÑÑÐ¸ÐºÐ¸, Ð½ÐµÐ´Ð¾ÑÑÐ¾Ð²ÐµÑÐ½ÑÑ ÑÐ°ÐºÑÐ¾Ð² Ð¸ ÐºÐ°ÑÐµÐ³Ð¾ÑÐ¸ÑÐ½ÑÑ Ð·Ð°ÑÐ²Ð»ÐµÐ½Ð¸Ð¹ Ð¾ ÑÐ¿Ð¾ÑÐ½ÑÑ Ð³Ð¸Ð¿Ð¾ÑÐµÐ·Ð°Ñ.
ÐÐµ Ð¿Ð¾Ð²ÑÐ¾ÑÑÐ¹ ÑÑÐ¸ Ð·Ð°Ð³Ð¾Ð»Ð¾Ð²ÐºÐ¸: {json.dumps(recent, ensure_ascii=False)}.
ÐÐµÑÐ½Ð¸ Ð¢ÐÐÐ¬ÐÐ JSON Ð¾Ð±ÑÐµÐºÑ ÑÐ¾ ÑÑÑÐ¾ÐºÐ¾Ð²ÑÐ¼Ð¸ ÐºÐ»ÑÑÐ°Ð¼Ð¸:
"title" â Ð·Ð°Ð³Ð¾Ð»Ð¾Ð²Ð¾Ðº Ð´Ð¾ 42 ÑÐ¸Ð¼Ð²Ð¾Ð»Ð¾Ð²;
"line1" â Ð¸Ð½ÑÑÐ¸Ð³ÑÑÑÐ¸Ð¹ ÑÐµÐ·Ð¸Ñ Ð´Ð¾ 32 ÑÐ¸Ð¼Ð²Ð¾Ð»Ð¾Ð²;
"line2" â Ð½ÐµÐ¾Ð¶Ð¸Ð´Ð°Ð½Ð½ÑÐ¹ Ð²ÑÐ²Ð¾Ð´ Ð´Ð¾ 32 ÑÐ¸Ð¼Ð²Ð¾Ð»Ð¾Ð²;
"paradox" â ÑÑÑÑ Ð¿Ð°ÑÐ°Ð´Ð¾ÐºÑÐ°, 1-2 Ð¿ÑÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ;
"evidence" â Ð¾Ð±ÑÑÑÐ½ÐµÐ½Ð¸Ðµ Ð¼ÐµÑÐ°Ð½Ð¸Ð·Ð¼Ð° Ð¸ Ð¸Ð·Ð²ÐµÑÑÐ½ÑÐ¹ Ð½Ð°ÑÑÐ½ÑÐ¹ Ð¿ÑÐ¸Ð½ÑÐ¸Ð¿/ÑÑÑÐµÐºÑ, 2-4 Ð¿ÑÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ, Ð±ÐµÐ· Ð²ÑÐ´ÑÐ¼Ð°Ð½Ð½ÑÑ ÑÑÑÐ»Ð¾Ðº;
"application" â Ð¿ÑÐ°ÐºÑÐ¸ÑÐµÑÐºÐ¸Ð¹ Ð¿ÑÐ¸Ð¼ÐµÑ, 2-3 Ð¿ÑÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ;
"experiment" â Ð¼ÑÑÐ»ÐµÐ½Ð½ÑÐ¹ ÑÐºÑÐ¿ÐµÑÐ¸Ð¼ÐµÐ½Ñ Ð¸Ð»Ð¸ Ð²Ð¾Ð¿ÑÐ¾Ñ, 1-2 Ð¿ÑÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ;
"topic" â Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ðµ ÑÐµÐ¼Ñ.
ÐÑÐµ Ð·Ð½Ð°ÑÐµÐ½Ð¸Ñ â ÑÑÑÐ¾ÐºÐ¸. ÐÐ°Ð³Ð¾Ð»Ð¾Ð²Ð¾Ðº Ð¸ ÐºÐ¾ÑÐ¾ÑÐºÐ¸Ðµ ÑÑÑÐ¾ÐºÐ¸ Ð¿Ð¾Ð½ÑÑÐ½Ñ Ð±ÐµÐ· ÐºÐ¾Ð½ÑÐµÐºÑÑÐ°.'''
    payload = {'contents': [{'parts': [{'text': prompt}]}],
               'generationConfig': {'temperature': 0.85, 'responseMimeType': 'application/json'}}
    errors = []
    for model in model_candidates(key):
        print(f'Trying Gemini model: {model}', flush=True)
        try:
            result = None
            for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
                try:
                    result = api_request('/' + model + ':generateContent', key, payload)
                    break
                except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
                    print(f'Temporary network error on {model}, attempt {attempt}: {exc}', flush=True)
                    if attempt == MAX_ATTEMPTS_PER_MODEL:
                        raise
                    time.sleep(2)
            if result is None:
                raise RuntimeError('No API response')
        except (RuntimeError, TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            msg = str(exc)
            errors.append(f'{model}: {msg[:450]}')
            print(f'Model failed: {model}: {msg[:450]}', flush=True)
            continue
        candidates = result.get('candidates') or []
        if not candidates:
            raise RuntimeError('Gemini returned no candidates: ' + json.dumps(result, ensure_ascii=False)[:1000])
        raw = ''.join(part.get('text', '') for part in candidates[0].get('content', {}).get('parts', []))
        idea = json.loads(raw)
        if not isinstance(idea, dict) or any(not isinstance(idea.get(k), str) or not idea[k].strip() for k in REQUIRED):
            raise ValueError('Gemini returned incomplete INSIGHT data')
        for field, limit in (('title', 42), ('line1', 32), ('line2', 32)):
            if len(idea[field]) > limit:
                raise ValueError(f'{field} is too long ({len(idea[field])} > {limit})')
        if idea['title'].casefold() in {x.casefold() for x in recent}:
            raise ValueError('Duplicate title')
        print(f'Using Gemini model: {model}', flush=True)
        return idea, now
    raise RuntimeError('All candidate models failed: ' + ' | '.join(errors))


def build(idea, now):
    base = json.loads(LATEST.read_text(encoding='utf-8'))
    if not base.get('families') or not base.get('views'):
        raise ValueError('Existing latest.json is not a valid Complicated configuration')
    header = f'INSIGHT Â· {now:%d.%m %H:%M}'
    body = (f"{idea['title']}\n\nÐÐ°ÑÐ°Ð´Ð¾ÐºÑ\n{idea['paradox']}\n\n"
            f"ÐÐ¾ÑÐµÐ¼Ñ ÑÑÐ¾ ÑÐ°Ð±Ð¾ÑÐ°ÐµÑ\n{idea['evidence']}\n\n"
            f"ÐÑÐ¸Ð¼ÐµÐ½ÐµÐ½Ð¸Ðµ\n{idea['application']}\n\n"
            f"ÐÑÑÐ»ÐµÐ½Ð½ÑÐ¹ ÑÐºÑÐ¿ÐµÑÐ¸Ð¼ÐµÐ½Ñ\n{idea['experiment']}")
    base['name'] = 'INSIGHT'
    base['showOnLockScreen'] = True
    base['views'] = [{'type': 'text', 'body': body}]
    for family in base['families']:
        for field, value in (('header', header), ('body1', idea['line1']), ('body2', idea['line2']),
                             ('line1', idea['line1']), ('line2', idea['line2']),
                             ('innerText', 'INSIGHT'), ('outerText', idea['line1']), ('text', idea['line1'])):
            if field in family:
                family[field] = value
    if not any(f.get('family') == 'graphicRectangular' for f in base['families']):
        raise ValueError('Missing required graphicRectangular family')
    return base


def main():
    if not LATEST.exists():
        raise RuntimeError('latest.json missing at repository root')
    history_file = ARCHIVE / 'index.json'
    history = json.loads(history_file.read_text(encoding='utf-8')) if history_file.exists() else []
    idea, now = generate(history)
    output = build(idea, now)
    ARCHIVE.mkdir(exist_ok=True)
    stamp = now.strftime('%Y-%m-%d_%H-%M')
    record = {'timestamp': now.isoformat(), **idea}
    (ARCHIVE / f'{stamp}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    history.append({'timestamp': now.isoformat(), 'title': idea['title'], 'topic': idea['topic']})
    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    LATEST.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Generated INSIGHT: {idea['title']}")


if __name__ == '__main__':
    try:
        main()
    except (KeyError, ValueError, OSError, RuntimeError, urllib.error.URLError) as exc:
        print(f'INSIGHT generation failed; no publication: {exc}', file=sys.stderr)
        sys.exit(1)