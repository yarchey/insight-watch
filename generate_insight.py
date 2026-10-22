#!/usr/bin/env python3
"""Generate and publish a Complicated-compatible INSIGHT JSON using Gemini."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
LATEST = ROOT / 'latest.json'
ARCHIVE = ROOT / 'archive'
MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')


def generate(history):
    key = os.environ['GEMINI_API_KEY']
    today = dt.datetime.now(ZoneInfo('Europe/Moscow'))
    recent = [x.get('title', '') for x in history[-30:]]
    prompt = f'''Ты редактор INSIGHT — интеллектуальных микроэссе для Apple Watch. Сейчас {today:%Y-%m-%d %H:%M} по Москве.
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
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent'
    payload = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'temperature': 0.9, 'responseMimeType': 'application/json'}}
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.load(response)
    raw = result['candidates'][0]['content']['parts'][0]['text']
    idea = json.loads(raw)
    required = ('title', 'line1', 'line2', 'paradox', 'evidence', 'application', 'experiment', 'topic')
    if any(not isinstance(idea.get(k), str) or not idea[k].strip() for k in required):
        raise ValueError('Gemini returned incomplete INSIGHT data')
    for k, limit in [('title', 42), ('line1', 32), ('line2', 32)]:
        if len(idea[k]) > limit:
            raise ValueError(f'{k} is too long ({len(idea[k])} > {limit})')
    if idea['title'].casefold() in {x.casefold() for x in recent}:
        raise ValueError('Duplicate title')
    return idea, today


def build(idea, now):
    # Preserve ALL complication families and template classes from the proven working file.
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
        for field, value in [('header', header), ('body1', idea['line1']), ('body2', idea['line2']),
                             ('line1', idea['line1']), ('line2', idea['line2']),
                             ('innerText', 'INSIGHT'), ('outerText', idea['line1']),
                             ('text', idea['line1'])]:
            if field in family:
                family[field] = value
    if not any(f.get('family') == 'graphicRectangular' for f in base['families']):
        raise ValueError('Missing required graphicRectangular family')
    return base


def main():
    if not LATEST.exists():
        raise RuntimeError('latest.json missing: keep the working file at repository root')
    ARCHIVE.mkdir(exist_ok=True)
    history_file = ARCHIVE / 'index.json'
    history = json.loads(history_file.read_text(encoding='utf-8')) if history_file.exists() else []
    idea, now = generate(history)
    output = build(idea, now)
    stamp = now.strftime('%Y-%m-%d_%H-%M')
    record = {'timestamp': now.isoformat(), **idea}
    # Only write after API call and JSON validation succeed.
    (ARCHIVE / f'{stamp}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    history.append({'timestamp': now.isoformat(), 'title': idea['title'], 'topic': idea['topic']})
    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    LATEST.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Published INSIGHT: {idea['title']}")


if __name__ == '__main__':
    try:
        main()
    except (KeyError, ValueError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f'INSIGHT generation failed; no publication: {exc}', file=sys.stderr)
        sys.exit(1)
