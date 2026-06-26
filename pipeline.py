"""
pipeline.py — PDF Pipeline core
Produces:
  1. presentation.pdf  — 15 clean visual slides (bullet points only, teacher margin)
  2. manuscript.pdf    — full narrator script per page (teleprompter style)
"""

import json, os, re, urllib.request
from io import BytesIO

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

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register Arial (supports Cyrillic, Latin, Uzbek)
pdfmetrics.registerFont(TTFont('Arial',       r'C:\Windows\Fonts\arial.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Bold',  r'C:\Windows\Fonts\arialbd.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Italic',r'C:\Windows\Fonts\ariali.ttf'))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial-Italic')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ─── Layout ───────────────────────────────────────────────────────────────────
# 16:9 page  (960 × 540 pt)
PAGE_W  = 960
PAGE_H  = 540
# Left column — presenter / camera zone (38%)
PRES_W  = int(PAGE_W * 0.38)
# Right column — slide content (58%)
C_X     = PRES_W + 24
C_W     = PAGE_W - C_X - 28
TOP_Y   = PAGE_H - 44
BOTTOM_Y = 22

# ─── TIU Logo ─────────────────────────────────────────────────────────────────
LOGO_PATH     = r'C:\Users\neovf\Desktop\work presentation_pdf\logo_tiu_cropped.png'
# Cropped logo is 343×151 px (ratio ~2.27:1) — fit to width 320pt inside presenter zone
LOGO_W        = 160
LOGO_H        = int(160 * 151 / 343)   # ≈ 70 pt, preserving aspect ratio
LOGO_X        = 10
LOGO_Y        = PAGE_H - LOGO_H - 10  # 10pt from top

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


# ─── Slide theme ──────────────────────────────────────────────────────────────
TH_BG      = '#f0ece4'
TH_BG2     = '#e8e3da'
TH_LINE    = '#ccc5b9'
TH_NAVY    = '#1a2a5e'
TH_TEXT    = '#1a2a5e'
TH_MUTED   = '#8a8fa8'
TH_GOLD    = '#ffd56a'
TH_GOLD2   = '#b8860b'
TH_RED     = '#b31e35'
TH_CYAN    = '#86d8e7'

# ─── Formula image ────────────────────────────────────────────────────────────
def render_formula(formula_text):
    try:
        fig, ax = plt.subplots(figsize=(4, 0.7))
        ax.set_facecolor(TH_BG)
        fig.patch.set_facecolor(TH_BG)
        ax.axis('off')
        f = formula_text.strip()
        if not (f.startswith('$') and f.endswith('$')): f = f'${f}$'
        ax.text(0.5, 0.5, f, fontsize=15, ha='center', va='center',
                color=TH_NAVY, transform=ax.transAxes,
                bbox=dict(boxstyle='round,pad=0.3', facecolor=TH_BG, edgecolor=TH_LINE))
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=TH_BG)
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        plt.close('all')
        return None

# ─── Presentation PDF ─────────────────────────────────────────────────────────
def build_presentation(doc_data, out_path):
    from reportlab.lib.utils import ImageReader

    title       = doc_data.get('title', 'Presentation')
    pages       = doc_data['pages']
    total_pages = doc_data.get('total_pages', len(pages))

    c = canvas.Canvas(out_path, pagesize=(PAGE_W, PAGE_H))

    title_style = ParagraphStyle('T', fontName='Arial-Bold', fontSize=22,
                                  leading=28, textColor=colors.HexColor(TH_NAVY),
                                  spaceAfter=0)
    bullet_style = ParagraphStyle('B', fontName='Arial', fontSize=17,
                                   leading=26, textColor=colors.HexColor(TH_NAVY),
                                   spaceAfter=0)

    for page in pages:
        n = page.get('page_num', 1)

        # ── Cream background ──────────────────────────────────────────────────
        c.setFillColor(colors.HexColor(TH_BG))
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        # ── Presenter zone (left 38%) ─────────────────────────────────────────
        c.setFillColor(colors.HexColor(TH_BG2))
        c.rect(0, 0, PRES_W, PAGE_H, fill=1, stroke=0)

        # Thin separator line
        c.setStrokeColor(colors.HexColor(TH_LINE))
        c.setLineWidth(0.8)
        c.line(PRES_W, 0, PRES_W, PAGE_H)

        # ── TIU Logo — top-left corner of presenter zone ──────────────────────
        if os.path.exists(LOGO_PATH):
            c.drawImage(LOGO_PATH, LOGO_X, LOGO_Y, width=LOGO_W, height=LOGO_H,
                        preserveAspectRatio=True, anchor='nw', mask='auto')

        # Page counter bottom-center of presenter zone
        c.setFont('Arial', 8)
        c.setFillColor(colors.HexColor(TH_MUTED))
        c.drawCentredString(PRES_W / 2, BOTTOM_Y + 6, f'{n} / {total_pages}')

        # ── Content zone (right 62%) ──────────────────────────────────────────
        # Text starts below logo height to avoid overlap, then uses full remaining space
        y = PAGE_H - 44

        # Title
        subtitle_text = (page.get('subtitle') or '').upper()
        sub = Paragraph(subtitle_text, title_style)
        sw, sh = sub.wrap(C_W, 140)
        sub.drawOn(c, C_X, y - sh)
        y -= sh + 18

        # Divider under title
        c.setStrokeColor(colors.HexColor(TH_NAVY))
        c.setLineWidth(1.2)
        c.line(C_X, y, C_X + C_W, y)
        y -= 22

        # Numbered bullets
        bullets = page.get('bullets', [])
        for i, bullet in enumerate(bullets, 1):
            line_txt = f'<b>{i}.</b> {bullet}'
            bp = Paragraph(line_txt, bullet_style)
            bw, bh = bp.wrap(C_W, 120)
            if y - bh < BOTTOM_Y + 14:
                break
            bp.drawOn(c, C_X, y - bh)
            y -= bh + 12

        # Formula
        formula = page.get('formula')
        if formula and y > BOTTOM_Y + 50:
            buf = render_formula(formula)
            if buf:
                img = ImageReader(buf)
                iw, ih = 200, 38
                fx = C_X + (C_W - iw) / 2
                c.drawImage(img, fx, y - ih - 6, width=iw, height=ih,
                            preserveAspectRatio=True, mask='auto')

        # Footer right
        c.setFont('Arial', 8)
        c.setFillColor(colors.HexColor(TH_MUTED))
        c.drawRightString(PAGE_W - 14, BOTTOM_Y, title[:55])

        c.showPage()
    c.save()

# ─── Manuscript PDF ───────────────────────────────────────────────────────────
def build_manuscript(doc_data, out_path):
    title       = doc_data.get('title', 'Manuscript')
    pages       = doc_data['pages']
    total_pages = doc_data.get('total_pages', len(pages))

    c = canvas.Canvas(out_path, pagesize=(PAGE_W, PAGE_H))

    sub_style    = ParagraphStyle('S', fontName='Arial-Bold', fontSize=15,
                                   leading=20, textColor=colors.HexColor(TH_NAVY),
                                   spaceAfter=6)
    script_style = ParagraphStyle('Sc', fontName='Arial', fontSize=13,
                                   leading=22, textColor=colors.HexColor(TH_TEXT),
                                   alignment=TA_JUSTIFY, spaceAfter=0)
    note_style   = ParagraphStyle('N', fontName='Arial-Italic', fontSize=9,
                                   textColor=colors.HexColor(TH_MUTED))

    for page in pages:
        n = page.get('page_num', 1)

        # ── Cream background ──────────────────────────────────────────────────
        c.setFillColor(colors.HexColor(TH_BG))
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        # ── Presenter zone (left 38%) ─────────────────────────────────────────
        c.setFillColor(colors.HexColor(TH_BG2))
        c.rect(0, 0, PRES_W, PAGE_H, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor(TH_LINE))
        c.setLineWidth(0.8)
        c.line(PRES_W, 0, PRES_W, PAGE_H)

        # ── TIU Logo — top-left corner of presenter zone ──────────────────────
        if os.path.exists(LOGO_PATH):
            c.drawImage(LOGO_PATH, LOGO_X, LOGO_Y, width=LOGO_W, height=LOGO_H,
                        preserveAspectRatio=True, anchor='nw', mask='auto')

        # Slide bullets preview in left zone (below logo)
        bullets = page.get('bullets', [])
        bx = 14
        by = LOGO_Y - 18   # start below the logo
        c.setFont('Arial-Bold', 8)
        c.setFillColor(colors.HexColor(TH_NAVY))
        c.drawString(bx, by, (page.get('subtitle', '') or '').upper()[:35])
        by -= 14
        for bi, bullet in enumerate(bullets[:4], 1):
            c.setFont('Arial', 7)
            c.setFillColor(colors.HexColor(TH_TEXT))
            c.drawString(bx, by, f'{bi}. {str(bullet or "")[:42]}')
            by -= 11

        # Page counter bottom of presenter zone
        c.setFont('Arial', 7)
        c.setFillColor(colors.HexColor(TH_MUTED))
        c.drawCentredString(PRES_W / 2, BOTTOM_Y + 6, f'{n} / {total_pages}')

        # ── Content zone (right 62%) — narration script ───────────────────────
        y = PAGE_H - 38

        sub = Paragraph((page.get('subtitle', '') or '').upper(), sub_style)
        sw, sh = sub.wrap(C_W, 80)
        sub.drawOn(c, C_X, y - sh)
        y -= sh + 8

        c.setStrokeColor(colors.HexColor(TH_NAVY))
        c.setLineWidth(1.0)
        c.line(C_X, y, C_X + C_W, y)
        y -= 16

        script = (page.get('manuscript') or page.get('content', '')).replace('\n', '<br/>')
        sp = Paragraph(script, script_style)
        sw, sh = sp.wrap(C_W, y - BOTTOM_Y - 20)
        sp.drawOn(c, C_X, y - sh)

        c.setFont('Arial', 7)
        c.setFillColor(colors.HexColor(TH_MUTED))
        c.drawRightString(PAGE_W - 14, BOTTOM_Y, f'SUFLYOR  ·  {title[:50]}')

        c.showPage()
    c.save()
