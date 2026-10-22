#!/usr/bin/env python3
"""Generate INSIGHT for Apple Watch Complicated using Gemini."""
import datetime as dt
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
LATEST = ROOT / 'latest.json'
ARCHIVE = ROOT / 'archive'
API = 'https://generativelanguage.googleapis.com/v1beta'
FIELDS = ('title', 'line1', 'line2', 'line3', 'paradox', 'evidence', 'application', 'experiment', 'topic')
MODELS = ('gemini-3.5-flash-lite', 'gemini-3-flash-preview', 'gemini-3.5-flash')
TOPICS = ('экономика', 'теория игр', 'психология', 'физика и космос', 'ИИ', 'сложные системы')


def request(path, key, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    headers = {'x-goog-api-key': key, 'Accept': 'application/json'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(API + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=35) as res:
            return json.load(res)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode('utf-8', errors='replace')[:700]
        raise RuntimeError(f'HTTP {exc.code}: {details}') from exc


def model_list(key):
    names, token = [], None
    while True:
        query = '?pageSize=100' + ('&pageToken=' + urllib.parse.quote(token, safe='') if token else '')
        page = request('/models' + query, key)
        names.extend(m['name'] for m in page.get('models', [])
                     if 'generateContent' in m.get('supportedGenerationMethods', []))
        token = page.get('nextPageToken')
        if not token:
            break
    configured = os.getenv('GEMINI_MODEL', '').strip().removeprefix('models/')
    preferred = ((configured,) if configured else MODELS)
    chosen = ['models/' + name for name in preferred if 'models/' + name in names]
    chosen += [name for name in names if name not in chosen and 'flash' in name.lower()]
    if not chosen:
        raise RuntimeError('No Flash models available. Listed: ' + ', '.join(names))
    return chosen


def generate(history, key):
    now = dt.datetime.now(ZoneInfo('Europe/Moscow'))
    topic = TOPICS[len(history) % len(TOPICS)]
    recent = [item.get('title', '') for item in history[-30:]]
    prompt = f'''Напиши один интеллектуальный INSIGHT на русском. Тема: {topic}.
Неожиданный, но научно обоснованный парадокс с практическим применением.
Не выдумывай источники, избегай банальностей. Не повторяй: {json.dumps(recent, ensure_ascii=False)}.
Ответ — только JSON-объект, все значения строки:
"title" (до 42 символов), "line1" (парадокс, до 24 символов),
"line2" (поворот, до 30 символов), "line3" (вывод, до 30 символов),
"paradox" (1–2 предложения), "evidence" (механизм, 2–4 предложения),
"application" (практика, 2–3 предложения), "experiment" (мысленный опыт), "topic".
Короткие строки самостоятельны, без даты, времени и слова INSIGHT.'''
    payload = {'contents': [{'parts': [{'text': prompt}]}],
               'generationConfig': {'temperature': 0.85, 'responseMimeType': 'application/json'}}
    errors = []
    for model in model_list(key):
        for attempt in (1, 2):
            print(f'Trying {model}, attempt {attempt}', flush=True)
            try:
                result = request('/' + model + ':generateContent', key, payload)
                raw = ''.join(p.get('text', '') for p in result['candidates'][0]['content']['parts'])
                idea = json.loads(raw)
                if not isinstance(idea, dict) or any(not isinstance(idea.get(k), str) or not idea[k].strip() for k in FIELDS):
                    raise ValueError('Incomplete JSON')
                for field, maximum in (('title', 42), ('line1', 24), ('line2', 30), ('line3', 30)):
                    if len(idea[field]) > maximum:
                        raise ValueError(f'{field} exceeds {maximum} characters')
                if idea['title'].casefold() in {title.casefold() for title in recent}:
                    raise ValueError('Repeated title')
                print(f'Generated using {model}: {idea["title"]}', flush=True)
                return idea, now
            except (OSError, RuntimeError, ValueError, KeyError, IndexError, TypeError) as exc:
                errors.append(f'{model}: {str(exc)[:250]}')
                if isinstance(exc, (TimeoutError, socket.timeout, urllib.error.URLError)) and attempt == 1:
                    time.sleep(2)
                    continue
                break
    raise RuntimeError('All models failed: ' + ' | '.join(errors))


def build(idea):
    base = json.loads(LATEST.read_text(encoding='utf-8'))
    families = base.get('families', [])
    if not any(f.get('family') == 'graphicRectangular' for f in families):
        raise ValueError('Missing graphicRectangular template in latest.json')
    base['name'] = 'INSIGHT'
    base['showOnLockScreen'] = True
    base['views'] = [{'type': 'text', 'body': (
        f"{idea['title']}\n\nПарадокс\n{idea['paradox']}\n\n"
        f"Объяснение\n{idea['evidence']}\n\nПрименение\n{idea['application']}\n\n"
        f"Мысленный эксперимент\n{idea['experiment']}")}]
    values = {'header': idea['line1'], 'body1': idea['line2'], 'body2': idea['line3'],
              'line1': idea['line1'], 'line2': idea['line2'], 'innerText': 'INSIGHT',
              'outerText': idea['line1'], 'text': idea['line1']}
    for family in families:
        for field in family.keys() & values.keys():
            family[field] = values[field]
    return base


def main():
    key = os.environ['GEMINI_API_KEY'].strip()
    if not key:
        raise ValueError('Empty GEMINI_API_KEY')
    if not LATEST.is_file():
        raise FileNotFoundError('latest.json is missing')
    index = ARCHIVE / 'index.json'
    history = json.loads(index.read_text(encoding='utf-8')) if index.exists() else []
    idea, now = generate(history, key)
    output = build(idea)
    ARCHIVE.mkdir(exist_ok=True)
    record = {'timestamp': now.isoformat(), **idea}
    (ARCHIVE / (now.strftime('%Y-%m-%d_%H-%M') + '.json')).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    history.append({'timestamp': now.isoformat(), 'title': idea['title'], 'topic': idea['topic']})
    index.write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    LATEST.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('INSIGHT JSON updated')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f'INSIGHT failed; existing JSON preserved if generation failed: {exc}', file=sys.stderr)
        sys.exit(1)
