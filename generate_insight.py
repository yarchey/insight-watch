#!/usr/bin/env python3
"""Generate INSIGHT for Complicated via a free-tier-compatible Gemini model."""
import datetime as dt
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
LATEST = ROOT / 'latest.json'
ARCHIVE = ROOT / 'archive'
API = 'https://generativelanguage.googleapis.com/v1beta'
REQUIRED = ('title', 'line1', 'line2', 'paradox', 'evidence', 'application', 'experiment', 'topic')


def api_request(path, key, payload=None):
    url = API + path
    headers = {'x-goog-api-key': key, 'Accept': 'application/json'}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method='POST' if data is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode('utf-8', errors='replace')[:1800]
        raise RuntimeError(f'Gemini API HTTP {exc.code}: {details}') from exc


def choose_model(key):
    configured = os.getenv('GEMINI_MODEL', '').strip()
    models = []
    page_token = None
    while True:
        suffix = '?pageSize=100'
        if page_token:
            suffix += '&pageToken=' + urllib.parse.quote(page_token, safe='')
        response = api_request('/models' + suffix, key)
        models.extend(m for m in response.get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    available = {m['name'].split('/')[-1]: m['name'] for m in models}
    if configured:
        name = configured.split('/')[-1]
        if name not in available:
            raise RuntimeError(f'GEMINI_MODEL={configured} unavailable. Available: {", ".join(sorted(available))}')
        return available[name]
    # Prefer fast, lower-cost models. Availability is checked for this specific key.
    preferences = ('gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash', 'gemini-3-flash-preview')
    for name in preferences:
        if name in available:
            return available[name]
    raise RuntimeError('No preferred Gemini model found. Available generateContent models: ' + ', '.join(sorted(available)))


def generate(history):
    key = os.environ['GEMINI_API_KEY'].strip()
    if not key:
        raise RuntimeError('GEMINI_API_KEY is empty')
    now = dt.datetime.now(ZoneInfo('Europe/Moscow'))
    recent = [x.get('title', '') for x in history[-30:]]
    prompt = f'''Ты редактор INSIGHT — интеллектуальных микроэссе для Apple Watch. Сейчас {now:%Y-%m-%d %H:%M} по Москве.
Создай ОДНУ неожиданную, интеллектуально честную идею на русском. Чередуй темы: экономика, теория игр, психология, физика/космос, ИИ/технологии, сложные системы. Избегай банальных цитат, мистики, недостоверных фактов и категоричных заявлений о спорных гипотезах.
Не повторяй эти недавние заголовки: {json.dumps(recent, ensure_ascii=False)}.
Верни ТОЛЬКО JSON объект со строковыми ключами:
"title" — заголовок до 42 символов;
"line1" — интригующий тезис до 32 символов;
"line2" — неожиданный вывод до 32 символов;
"paradox" — суть парадокса, 1-2 предложения;
"evidence" — объяснение механизма и известный научный принцип/эффект, 2-4 предложения, без выдуманных ссылок;
"application" — практический пример, 2-3 предложения;
"experiment" — мысленный эксперимент или вопрос, 1-2 предложения;
"topic" — название темы.
Заголовок и строки должны быть понятны без контекста. Все значения — текст, не массивы.'''
    model = choose_model(key)
    print(f'Using Gemini model: {model}', flush=True)
    payload = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'temperature': 0.9, 'responseMimeType': 'application/json'}}
    response = api_request('/' + model + ':generateContent', key, payload)
    candidates = response.get('candidates') or []
    if not candidates:
        raise RuntimeError('Gemini returned no candidates: ' + json.dumps(response, ensure_ascii=False)[:1000])
    raw = ''.join(p.get('text', '') for p in candidates[0].get('content', {}).get('parts', []))
    idea = json.loads(raw)
    if not isinstance(idea, dict) or any(not isinstance(idea.get(k), str) or not idea[k].strip() for k in REQUIRED):
        raise ValueError('Gemini returned incomplete INSIGHT data')
    for k, limit in (('title', 42), ('line1', 32), ('line2', 32)):
        if len(idea[k]) > limit:
            raise ValueError(f'{k} is too long ({len(idea[k])} > {limit})')
    if idea['title'].casefold() in {x.casefold() for x in recent}:
        raise ValueError('Duplicate title')
    return idea, now


def build(idea, now):
    base = json.loads(LATEST.read_text(encoding='utf-8'))
    if not base.get('families') or not base.get('views'):
        raise ValueError('Existing latest.json is not a valid Complicated configuration')
    header = f'INSIGHT · {now:%d.%m %H:%M}'
    body = (f"{idea['title']}\n\nПарадокс\n{idea['paradox']}\n\n"
            f"Почему это работает\n{idea['evidence']}\n\n"
            f"Применение\n{idea['application']}\n\n"
            f"Мысленный эксперимент\n{idea['experiment']}")
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
