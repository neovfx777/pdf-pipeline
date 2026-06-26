"""
pipeline.py — PDF Pipeline core
Produces:
  1. presentation.pdf  — 15 clean visual slides (bullet points only, teacher margin)
  2. manuscript.pdf    — full narrator script per page (teleprompter style)
"""

import json, os, re, urllib.request

LANGUAGE_NAMES = {
    'af':'Afrikaans','ar':'Arabic','bg':'Bulgarian','bn':'Bengali','ca':'Catalan',
    'cs':'Czech','cy':'Welsh','da':'Danish','de':'German','el':'Greek',
    'en':'English','es':'Spanish','et':'Estonian','fa':'Persian','fi':'Finnish',
    'fr':'French','gu':'Gujarati','he':'Hebrew','hi':'Hindi','hr':'Croatian',
    'hu':'Hungarian','hy':'Armenian','id':'Indonesian','it':'Italian','ja':'Japanese',
    'ka':'Georgian','ko':'Korean','lt':'Lithuanian','lv':'Latvian','mk':'Macedonian',
    'ml':'Malayalam','mr':'Marathi','nl':'Dutch','no':'Norwegian','pl':'Polish',
    'pt':'Portuguese','ro':'Romanian','ru':'Russian','sk':'Slovak','sl':'Slovenian',
    'sq':'Albanian','sr':'Serbian','sv':'Swedish','sw':'Swahili','ta':'Tamil',
    'te':'Telugu','th':'Thai','tl':'Filipino','tr':'Turkish','uk':'Ukrainian',
    'ur':'Urdu','uz':'Uzbek','vi':'Vietnamese','zh-cn':'Chinese (Simplified)','zh-tw':'Chinese (Traditional)',
}

def detect_language(text):
    try:
        from langdetect import detect
        code = detect(text[:3000])
        return {'code': code, 'name': LANGUAGE_NAMES.get(code, code.upper())}
    except Exception:
        return {'code': 'en', 'name': 'English'}

# PDF rendering is handled by the separate design engine
from pdf_engine import build_presentation, build_manuscript

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"

def calculate_pages(text):
    words = len(text.split())
    return max(15, min(25, words // 150))

# ─── Text extraction ──────────────────────────────────────────────────────────
def extract_text(file_path, ext):
    ext = ext.lower().lstrip('.')
    if ext == 'txt':
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    elif ext == 'docx':
        from docx import Document
        return '\n'.join(p.text for p in Document(file_path).paragraphs if p.text.strip())
    elif ext == 'pdf':
        import pdfplumber
        parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: parts.append(t)
        return '\n'.join(parts)
    raise ValueError(f"Unsupported: {ext}")

# ─── AI generation ────────────────────────────────────────────────────────────
def ask_ollama(prompt, model=OLLAMA_MODEL):
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": -1}
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["response"]

def _extract_outermost(text):
    start = text.find('{')
    if start == -1:
        return None
    depth, in_str, escape = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return text[start:]

def parse_json_robust(raw):
    from json_repair import repair_json
    fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    candidate = fence.group(1).strip() if fence else raw
    blob = _extract_outermost(candidate) or candidate
    try:
        result = json.loads(blob)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r',\s*([\}\]])', r'\1', blob)
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    try:
        repaired = repair_json(blob, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
    except Exception:
        pass
    raise ValueError("Could not extract valid JSON from AI response.")

def _batch_prompt(text_chunk, page_start, page_end, title, language):
    pages_json = ',\n    '.join(
        f'{{"page_num":{n},"subtitle":"...","bullets":["...","...","..."],"formula":null,"manuscript":"..."}}'
        for n in range(page_start, page_end + 1)
    )
    return (
        f'IMPORTANT: You MUST write every word of your response in {language}. '
        f'Do NOT use any other language. Even if the source text is in a different language, '
        f'translate everything into {language}.\n\n'
        f'You are a video lesson scriptwriter. Topic: {title}\n\n'
        f'Based on the text below, write slides for pages {page_start} to {page_end}.\n'
        f'Each page needs:\n'
        f'- subtitle: slide title, max 6 words, written in {language}\n'
        f'- bullets: 3-5 bullet points, max 8 words each, written in {language}\n'
        f'- formula: LaTeX math formula if relevant, else null\n'
        f'- manuscript: 4-6 sentences spoken by presenter, written in {language}\n\n'
        f'Source text:\n{text_chunk}\n\n'
        f'Return ONLY a JSON array, no explanation, no extra text:\n'
        f'[\n    {pages_json}\n]\n'
        f'\nRemember: ALL text must be in {language} only.'
    )

def _get_title(text, model, language):
    prompt = (
        f'You must respond in {language} only. No other language allowed.\n'
        f'Write a short course title (4-6 words) in {language} for this text.\n'
        f'Return ONLY the title text, no quotes, no explanation.\n'
        f'TEXT: {text[:600]}'
    )
    for _ in range(3):
        raw = ask_ollama(prompt, model).strip().strip('"').strip()
        if raw and len(raw) < 80 and '\n' not in raw:
            return raw
    return 'Presentation'

def generate_pages(text, model=OLLAMA_MODEL, language='English'):
    num_pages = calculate_pages(text)
    title = _get_title(text, model, language)
    BATCH = 5
    all_pages = []
    page_num = 1
    while page_num <= num_pages:
        page_end = min(page_num + BATCH - 1, num_pages)
        batch_count = page_end - page_num + 1
        t_start = int((page_num - 1) / num_pages * len(text))
        t_end   = int(page_end / num_pages * len(text))
        chunk = text[t_start:t_end] or text[:2000]
        prompt = _batch_prompt(chunk, page_num, page_end, title, language)
        for attempt in range(3):
            raw = ask_ollama(prompt, model)
            try:
                stripped = raw.strip()
                fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', stripped)
                if fence:
                    stripped = fence.group(1).strip()
                arr_match = re.search(r'\[[\s\S]*\]', stripped)
                if arr_match:
                    from json_repair import repair_json
                    blob = arr_match.group()
                    try:
                        batch = json.loads(blob)
                    except Exception:
                        batch = repair_json(blob, return_objects=True)
                else:
                    doc = parse_json_robust(raw)
                    batch = doc.get('pages', [])
                if not isinstance(batch, list) or len(batch) == 0:
                    raise ValueError("Empty batch")
                for i, pg in enumerate(batch):
                    pg['page_num'] = page_num + i
                    if 'content' in pg and 'manuscript' not in pg:
                        pg['manuscript'] = pg.pop('content')
                    pg.setdefault('manuscript', '')
                    pg.setdefault('bullets', [])
                    pg.setdefault('formula', None)
                all_pages.extend(batch[:batch_count])
                break
            except Exception:
                if attempt == 2:
                    for i in range(batch_count):
                        all_pages.append({
                            'page_num': page_num + i,
                            'subtitle': f'Page {page_num + i}',
                            'bullets': [],
                            'formula': None,
                            'manuscript': ''
                        })
                continue
        page_num = page_end + 1
    return {'title': title, 'total_pages': num_pages, 'pages': all_pages}

def revise_page(page, instruction, model=OLLAMA_MODEL, language='English'):
    prompt = f"""Revise this video lesson page based on the instruction.
CRITICAL LANGUAGE RULE: ALL output must be written exclusively in {language}. No other language allowed.
Return ONLY valid JSON for the single page:

Current:
{json.dumps(page, indent=2)}

Instruction: {instruction}

Return:
{{
  "page_num": {page['page_num']},
  "subtitle": "...",
  "bullets": ["...", "..."],
  "formula": null,
  "manuscript": "..."
}}"""
    raw = ask_ollama(prompt, model)
    result = parse_json_robust(raw)
    result['page_num'] = page['page_num']
    return result


