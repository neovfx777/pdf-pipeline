"""
pdf_engine.py — Professional PDF rendering engine for TIU PDF Pipeline
Modular design system with reusable components and multiple layout templates.
Content generation is untouched — only visual presentation is handled here.
"""

import os
from io import BytesIO
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ═══════════════════════════════════════════════════════════════════════════════
#  DESIGN SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

# — Color palette —
NAVY        = '#1a2a5e'
NAVY_MID    = '#2d4080'
GOLD        = '#c9a84c'
GOLD_LIGHT  = '#f5ead8'
CREAM       = '#f4f1eb'
CREAM_D     = '#e6e1d6'
BLUE_SOFT   = '#ebf0f8'
GRAY_TEXT   = '#3d4a5c'
GRAY_LIGHT  = '#dde2ea'
MUTED       = '#8892a4'
WHITE       = '#ffffff'
GREEN_BG    = '#edf7ed'
GREEN_TEXT  = '#1a4a1a'

# — Spacing scale (pt) —
SP1, SP2, SP3, SP4, SP5 = 8, 16, 24, 32, 48

# — Type scale —
FS_DISPLAY = 22
FS_HEADING = 16
FS_BODY    = 14
FS_SMALL   = 11
FS_CAPTION = 9
FS_FOOTER  = 8

# — Page geometry (16:9) —
PAGE_W   = 960
PAGE_H   = 540
PRES_W   = int(PAGE_W * 0.38)      # 364  presenter / camera zone
STRIPE_W = 6                         # navy divider stripe width
C_X      = PRES_W + SP2             # 380  content zone left edge
C_W      = PAGE_W - C_X - SP2       # 564  content zone width
FOOTER_H = 22                        # navy footer bar
TOP_BAND = 5                         # gold+navy top accent strip
HDR_H    = 44                        # slide title bar height

# — Content body limits —
TITLE_BOT = PAGE_H - TOP_BAND - HDR_H    # 491  bottom of title bar
BODY_TOP  = TITLE_BOT - SP2              # 475  body starts
BODY_BOT  = FOOTER_H + SP2              # 38   body ends

# — Logo —
LOGO_PATH = r'C:\Users\neovf\Desktop\work presentation_pdf\logo_tiu_cropped.png'
LOGO_W    = 160
LOGO_H    = int(160 * 151 / 343)         # ≈ 70 pt
LOGO_X    = 10
LOGO_Y    = PAGE_H - LOGO_H - 10

# — Reusable constants —
RADIUS    = 4
COL_GAP   = SP2

# ── Font registration ─────────────────────────────────────────────────────────
try:
    pdfmetrics.registerFont(TTFont('Arial',        r'C:\Windows\Fonts\arial.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-Bold',   r'C:\Windows\Fonts\arialbd.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-Italic', r'C:\Windows\Fonts\ariali.ttf'))
    pdfmetrics.registerFontFamily('Arial',
        normal='Arial', bold='Arial-Bold', italic='Arial-Italic')
except Exception:
    pass

# ── Paragraph style factory ───────────────────────────────────────────────────
def _ps(name, font='Arial', size=FS_BODY, color=GRAY_TEXT,
        leading=None, align=TA_LEFT, li=0, sa=0, sb=0):
    return ParagraphStyle(
        name, fontName=font, fontSize=size,
        leading=leading or round(size * 1.45),
        textColor=colors.HexColor(color),
        alignment=align, leftIndent=li, spaceAfter=sa, spaceBefore=sb)

# Pre-built styles
S_SLIDE_TITLE = _ps('pe_st',  font='Arial-Bold', size=FS_DISPLAY, color=WHITE, leading=30)
S_HEADING     = _ps('pe_h',   font='Arial-Bold', size=FS_HEADING, color=NAVY)
S_BODY        = _ps('pe_b',   size=FS_BODY,  color=GRAY_TEXT, leading=22)
S_BODY_J      = _ps('pe_bj',  size=FS_BODY,  color=GRAY_TEXT, leading=22, align=TA_JUSTIFY)
S_BODY_SM     = _ps('pe_bs',  size=12,       color=GRAY_TEXT, leading=18)
S_SMALL       = _ps('pe_s',   size=FS_SMALL, color=MUTED)
S_SMALL_NAVY  = _ps('pe_sn',  font='Arial-Bold', size=FS_SMALL, color=NAVY)
S_CARD_HDR    = _ps('pe_ch',  font='Arial-Bold', size=13,       color=NAVY)
S_CARD_BODY   = _ps('pe_cb',  size=FS_SMALL, color=GRAY_TEXT, leading=15)
S_CONCEPT     = _ps('pe_co',  font='Arial-Bold', size=16,       color=NAVY, leading=24)
S_DEF         = _ps('pe_df',  font='Arial-Italic', size=FS_BODY, color=GRAY_TEXT,
                     leading=22, align=TA_JUSTIFY)
S_FOOTER      = _ps('pe_ft',  size=FS_FOOTER, color='#d6d0c4')
S_MANU_TITLE  = _ps('pe_mt',  font='Arial-Bold', size=18, color=WHITE, leading=24)
S_MANU_BODY   = _ps('pe_mb',  size=16, color=GRAY_TEXT, leading=28, align=TA_JUSTIFY)
S_MANU_SMALL  = _ps('pe_ms',  size=FS_SMALL, color=MUTED)
S_CHECKMARK   = _ps('pe_ck',  size=FS_BODY,  color=NAVY, leading=24)
S_BANNER      = _ps('pe_bn',  font='Arial-Bold', size=12, color=NAVY)


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE STRUCTURE COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

def page_base(c, page_num, total_pages, course_title=''):
    """
    Draws the shared structural elements present on every page:
    background, presenter zone, logo, page badge, footer bar, top accent.
    """
    # Cream background
    c.setFillColor(colors.HexColor(CREAM))
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Presenter zone (slightly darker cream)
    c.setFillColor(colors.HexColor(CREAM_D))
    c.rect(0, 0, PRES_W, PAGE_H, fill=1, stroke=0)

    # Navy vertical stripe (right edge of presenter zone)
    c.setFillColor(colors.HexColor(NAVY))
    c.rect(PRES_W - STRIPE_W, FOOTER_H, STRIPE_W, PAGE_H - FOOTER_H, fill=1, stroke=0)

    # TIU logo
    if os.path.exists(LOGO_PATH):
        c.drawImage(LOGO_PATH, LOGO_X, LOGO_Y,
                    width=LOGO_W, height=LOGO_H,
                    preserveAspectRatio=True, anchor='nw', mask='auto')

    # Page badge — navy rounded rect with white text
    bw, bh, br = 58, 20, 5
    bx = (PRES_W - STRIPE_W - bw) // 2
    by_b = FOOTER_H + SP1 + 2
    c.setFillColor(colors.HexColor(NAVY))
    c.roundRect(bx, by_b, bw, bh, br, fill=1, stroke=0)
    c.setFont('Arial-Bold', FS_FOOTER)
    c.setFillColor(colors.white)
    c.drawCentredString(bx + bw / 2, by_b + 6, f'{page_num}  /  {total_pages}')

    # Full-width navy footer bar
    c.setFillColor(colors.HexColor(NAVY))
    c.rect(0, 0, PAGE_W, FOOTER_H, fill=1, stroke=0)

    # Course title inside footer
    if course_title:
        p = Paragraph(str(course_title)[:80], S_FOOTER)
        pw, ph = p.wrap(C_W - SP3, FOOTER_H)
        p.drawOn(c, C_X, (FOOTER_H - ph) / 2)

    # Gold top accent (content zone width minus navy corner)
    c.setFillColor(colors.HexColor(GOLD))
    c.rect(C_X, PAGE_H - TOP_BAND, C_W - 56, TOP_BAND, fill=1, stroke=0)

    # Navy corner block top-right (56 pt wide)
    c.setFillColor(colors.HexColor(NAVY))
    c.rect(PAGE_W - 56, PAGE_H - TOP_BAND, 56, TOP_BAND, fill=1, stroke=0)


def slide_title_bar(c, subtitle_text):
    """
    Draws navy title bar with white title text and gold bottom edge.
    Returns y coordinate just below the bar (body starts here).
    """
    bar_y = PAGE_H - TOP_BAND - HDR_H
    # Navy background
    c.setFillColor(colors.HexColor(NAVY))
    c.rect(C_X, bar_y, C_W, HDR_H, fill=1, stroke=0)
    # White title text
    p = Paragraph(subtitle_text.upper(), S_SLIDE_TITLE)
    pw, ph = p.wrap(C_W - SP4, HDR_H)
    p.drawOn(c, C_X + SP2, bar_y + (HDR_H - ph) / 2)
    # Gold bottom accent on title bar
    c.setFillColor(colors.HexColor(GOLD))
    c.rect(C_X, bar_y, C_W, 3, fill=1, stroke=0)
    return bar_y - SP2  # body starts here


# ═══════════════════════════════════════════════════════════════════════════════
#  CONTENT COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

def bullet_list(c, bullets, x, y, w, floor, style=None, sq_color=NAVY):
    """
    Navy-square bullet list with subtle separators between items.
    Returns y after last drawn item.
    """
    st  = style or S_BODY
    sq  = 6
    ind = SP2 + 2

    for i, bullet in enumerate(bullets):
        text = str(bullet or '').strip()
        if not text:
            continue
        p = Paragraph(text, st)
        pw, ph = p.wrap(w - ind, 200)
        if y - ph < floor:
            break
        # Navy square marker
        c.setFillColor(colors.HexColor(sq_color))
        c.rect(x, y - sq + 2, sq, sq, fill=1, stroke=0)
        p.drawOn(c, x + ind, y - ph)
        y -= ph + SP1

        # Thin separator (not after last bullet)
        if i < len(bullets) - 1 and y - 4 > floor:
            c.setStrokeColor(colors.HexColor(GRAY_LIGHT))
            c.setLineWidth(0.3)
            c.line(x + ind, y + 4, x + w, y + 4)
            y -= 4

    return y


def key_point_box(c, text, x, y, w, label='KEY CONCEPT'):
    """
    Soft-blue card with gold left border and concept text.
    Returns y after box.
    """
    if not text:
        return y
    p = Paragraph(str(text), S_CONCEPT)
    pw, ph = p.wrap(w - SP5 - 4, 200)
    box_h = ph + SP3 + SP2
    box_y = y - box_h

    if box_y < BODY_BOT:
        box_h = y - BODY_BOT
        box_y = BODY_BOT

    # Soft blue fill
    c.setFillColor(colors.HexColor(BLUE_SOFT))
    c.roundRect(x, box_y, w, box_h, RADIUS, fill=1, stroke=0)
    # Gold left border
    c.setFillColor(colors.HexColor(GOLD))
    c.roundRect(x, box_y, 4, box_h, 2, fill=1, stroke=0)
    # Label
    lp = Paragraph(label, S_SMALL_NAVY)
    lw, lh = lp.wrap(w - SP5, 20)
    lp.drawOn(c, x + SP3, box_y + box_h - lh - SP1)
    # Body text
    p.drawOn(c, x + SP3, box_y + (box_h - ph) / 2 - SP1)

    return box_y - SP2


def definition_card(c, text, x, y, w, label='DEFINITION'):
    """
    Italic definition card with gold left border on light-gold background.
    Returns y after card.
    """
    if not text:
        return y
    p = Paragraph(f'"{str(text)}"', S_DEF)
    pw, ph = p.wrap(w - SP5, 200)
    pad   = SP2
    box_h = ph + pad * 2 + SP2
    box_y = y - box_h

    # Light gold background
    c.setFillColor(colors.HexColor(GOLD_LIGHT))
    c.roundRect(x, box_y, w, box_h, RADIUS, fill=1, stroke=0)
    # Gold left border
    c.setFillColor(colors.HexColor(GOLD))
    c.roundRect(x, box_y, 5, box_h, 2, fill=1, stroke=0)
    # Label
    lp = Paragraph(label, S_SMALL_NAVY)
    lw, lh = lp.wrap(w - SP5, 16)
    lp.drawOn(c, x + SP3, box_y + box_h - lh - SP1)
    # Text
    p.drawOn(c, x + SP3, box_y + pad)

    return box_y - SP2


def two_column(c, left_bullets, right_text, x, y, w, floor,
               right_label='KEY CONCEPT'):
    """
    Left: bullet list.  Right: key-point box.
    Returns lowest y reached.
    """
    col_w = (w - COL_GAP) / 2
    y_l = bullet_list(c, left_bullets, x, y, col_w, floor)
    y_r = key_point_box(c, right_text, x + col_w + COL_GAP, y, col_w,
                        label=right_label)
    return min(y_l, y_r)


def summary_banner(c, x, y, w, label='KEY TAKEAWAYS'):
    """Draws gold banner heading. Returns y after it."""
    bh = 28
    c.setFillColor(colors.HexColor(GOLD_LIGHT))
    c.roundRect(x, y - bh, w, bh, RADIUS, fill=1, stroke=0)
    c.setFillColor(colors.HexColor(GOLD))
    c.roundRect(x, y - bh, 4, bh, 2, fill=1, stroke=0)
    p = Paragraph(label, S_BANNER)
    pw, ph = p.wrap(w - SP5, bh)
    p.drawOn(c, x + SP3, y - bh + (bh - ph) / 2)
    return y - bh - SP2


def number_badge(c, cx, cy, number, radius=13):
    """Draws a navy circle badge with white number."""
    c.setFillColor(colors.HexColor(NAVY))
    c.circle(cx, cy, radius, fill=1, stroke=0)
    c.setFont('Arial-Bold', 10)
    c.setFillColor(colors.white)
    c.drawCentredString(cx, cy - 4, str(number))


def formula_box(c, formula_buf, x, y, w):
    """Thin-bordered box containing a formula image. Returns y after box."""
    if not formula_buf:
        return y
    from reportlab.lib.utils import ImageReader
    img = ImageReader(formula_buf)
    iw, ih = 180, 32
    fx  = x + (w - iw) / 2
    fy  = y - ih - SP2
    pad = SP1
    c.setStrokeColor(colors.HexColor(NAVY))
    c.setLineWidth(0.6)
    c.roundRect(fx - pad, fy - pad, iw + pad * 2, ih + pad * 2,
                RADIUS, fill=0, stroke=1)
    c.drawImage(img, fx, fy, width=iw, height=ih,
                preserveAspectRatio=True, mask='auto')
    return fy - pad - SP2


def render_formula(text):
    """Render a LaTeX formula to a PNG BytesIO buffer."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(4, 0.7))
        ax.axis('off')
        fig.patch.set_facecolor(CREAM)
        ax.set_facecolor(CREAM)
        f = text.strip()
        if not (f.startswith('$') and f.endswith('$')):
            f = f'${f}$'
        ax.text(0.5, 0.5, f, fontsize=14, ha='center', va='center',
                color=NAVY, transform=ax.transAxes)
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                    facecolor=CREAM)
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except Exception:
            pass
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  LAYOUT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

def _tpl_standard(c, bullets, fbuf, x, y, w, floor):
    """Enhanced bullet list with navy squares and subtle separators."""
    y = bullet_list(c, bullets, x, y, w, floor)
    if fbuf and y > floor + 50:
        y = formula_box(c, fbuf, x, y, w)
    return y


def _tpl_two_column(c, bullets, fbuf, x, y, w, floor):
    """Left: bullets. Right: key concept box highlighting bullet[0]."""
    if len(bullets) < 2:
        return _tpl_standard(c, bullets, fbuf, x, y, w, floor)
    split  = max(1, (len(bullets) + 1) // 2)
    left   = bullets[:split]
    right  = bullets[0]
    y = two_column(c, left, right, x, y, w, floor)
    if fbuf and y > floor + 50:
        y = formula_box(c, fbuf, x, y, w)
    return y


def _tpl_concept(c, bullets, fbuf, x, y, w, floor):
    """Large key-point box for bullet[0], smaller bullets below."""
    if not bullets:
        return y
    y = key_point_box(c, bullets[0], x, y, w)
    if len(bullets) > 1 and y > floor + SP3:
        y -= SP1
        y = bullet_list(c, bullets[1:], x, y, w, floor, style=S_BODY_SM)
    if fbuf and y > floor + 50:
        y = formula_box(c, fbuf, x, y, w)
    return y


def _tpl_definition(c, bullets, fbuf, x, y, w, floor):
    """Definition card for bullet[0], remaining bullets below."""
    if not bullets:
        return y
    y = definition_card(c, bullets[0], x, y, w)
    if len(bullets) > 1 and y > floor + SP3:
        y -= SP1
        y = bullet_list(c, bullets[1:], x, y, w, floor)
    if fbuf and y > floor + 50:
        y = formula_box(c, fbuf, x, y, w)
    return y


def _tpl_summary(c, bullets, fbuf, x, y, w, floor):
    """Gold takeaway banner with checkmark-prefixed bullets."""
    y = summary_banner(c, x, y, w)
    for bullet in bullets:
        text = f'<font color="{GOLD}">✓</font>   {str(bullet or "")}'
        p    = Paragraph(text, S_CHECKMARK)
        pw, ph = p.wrap(w - SP3, 80)
        if y - ph < floor:
            break
        p.drawOn(c, x + SP2, y - ph)
        y -= ph + SP1
    return y


# ── Template selector ─────────────────────────────────────────────────────────
_ROTATION = [_tpl_standard, _tpl_two_column, _tpl_concept, _tpl_definition]

def pick_template(page_num, total_pages, bullets):
    if page_num == total_pages:
        return _tpl_summary
    if len(bullets) <= 3 and page_num % 3 == 0:
        return _tpl_concept
    return _ROTATION[(page_num - 1) % len(_ROTATION)]


# ═══════════════════════════════════════════════════════════════════════════════
#  BUILD FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def build_presentation(doc_data, out_path):
    """Build the 16:9 slide-deck PDF."""
    title       = doc_data.get('title', 'Presentation')
    pages       = doc_data['pages']
    total_pages = doc_data.get('total_pages', len(pages))

    c = rl_canvas.Canvas(out_path, pagesize=(PAGE_W, PAGE_H))

    for page in pages:
        n       = page.get('page_num', 1)
        sub     = (page.get('subtitle') or '').strip()
        bullets = [b for b in (page.get('bullets') or []) if b]
        formula = page.get('formula')
        fbuf    = render_formula(formula) if formula else None

        # ── Shared base structure ─────────────────────────────────────────────
        page_base(c, n, total_pages, title)

        # ── Title bar → returns y where body starts ───────────────────────────
        y = slide_title_bar(c, sub)

        # ── Content body ──────────────────────────────────────────────────────
        tpl = pick_template(n, total_pages, bullets)
        tpl(c, bullets, fbuf,
            x=C_X + SP2, y=y, w=C_W - SP3, floor=BODY_BOT)

        c.showPage()

    c.save()


def build_manuscript(doc_data, out_path):
    """Build the teleprompter / presenter script PDF."""
    title       = doc_data.get('title', 'Manuscript')
    pages       = doc_data['pages']
    total_pages = doc_data.get('total_pages', len(pages))

    c = rl_canvas.Canvas(out_path, pagesize=(PAGE_W, PAGE_H))

    for page in pages:
        n       = page.get('page_num', 1)
        sub     = (page.get('subtitle') or '').strip()
        bullets = [b for b in (page.get('bullets') or []) if b]
        script  = (page.get('manuscript') or page.get('content') or '').strip()

        # Estimated speaking time (~130 wpm)
        wc   = len(script.split())
        secs = int(wc / 130 * 60)
        etime = f'{secs // 60}:{secs % 60:02d}'

        # ── Shared base structure ─────────────────────────────────────────────
        page_base(c, n, total_pages, f'SUFLYOR  ·  {title}')

        # ── Presenter zone: mini slide preview (below logo) ───────────────────
        prev_y = LOGO_Y - SP2
        c.setFont('Arial-Bold', 7)
        c.setFillColor(colors.HexColor(NAVY))
        c.drawString(LOGO_X, prev_y, sub.upper()[:36])
        prev_y -= 12

        for bi, b in enumerate(bullets[:5], 1):
            # Tiny square marker
            c.setFillColor(colors.HexColor(NAVY))
            c.rect(LOGO_X, prev_y - 4, 4, 4, fill=1, stroke=0)
            c.setFont('Arial', 7)
            c.setFillColor(colors.HexColor(GRAY_TEXT))
            c.drawString(LOGO_X + 8, prev_y, str(b or '')[:38])
            prev_y -= 11

        # ── Script title bar ──────────────────────────────────────────────────
        bar_y = PAGE_H - TOP_BAND - HDR_H
        c.setFillColor(colors.HexColor(NAVY))
        c.rect(C_X, bar_y, C_W, HDR_H, fill=1, stroke=0)
        # Gold bottom accent
        c.setFillColor(colors.HexColor(GOLD))
        c.rect(C_X, bar_y, C_W, 3, fill=1, stroke=0)
        # Subtitle title
        tp = Paragraph(sub.upper(), S_MANU_TITLE)
        tw, th = tp.wrap(C_W - SP5 - 60, HDR_H)
        tp.drawOn(c, C_X + SP2, bar_y + (HDR_H - th) / 2)
        # Speaking time (gold, right)
        c.setFont('Arial', FS_SMALL)
        c.setFillColor(colors.HexColor(GOLD))
        c.drawRightString(C_X + C_W - SP2,
                          bar_y + (HDR_H - FS_SMALL) / 2, f'≈ {etime} min')

        # ── Narration text with navy left border ──────────────────────────────
        text_y   = bar_y - SP2
        text_x   = C_X + SP3          # indented from navy 3pt border
        text_w   = C_W - SP4 - SP1
        floor_y  = FOOTER_H + SP2

        sp_obj = Paragraph(script.replace('\n', '<br/>'), S_MANU_BODY)
        sw, sh = sp_obj.wrap(text_w, text_y - floor_y)

        # 3pt navy left border line
        border_top = text_y
        border_bot = max(floor_y, text_y - sh)
        c.setFillColor(colors.HexColor(NAVY))
        c.rect(C_X, border_bot, 3, border_top - border_bot, fill=1, stroke=0)

        sp_obj.drawOn(c, text_x, text_y - sh)

        c.showPage()

    c.save()
