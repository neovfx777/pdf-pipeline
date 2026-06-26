"""
telegram_bot.py — Telegram bot for PDF Pipeline
Foydalanuvchi .txt/.docx/.pdf yoki tekst yuborsa => 15 sahifali 2 ta PDF qaytaradi
Run: python telegram_bot.py
"""

import os, sys, json, time, uuid, threading, traceback
import urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import extract_text, generate_pages, build_presentation, build_manuscript

TOKEN    = '8893623241:AAF2dQ8OsudZwiec7em5MdZIV9u-PScvU98'
API      = f'https://api.telegram.org/bot{TOKEN}'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR  = os.path.join(BASE_DIR, 'output')
UPL_DIR  = os.path.join(BASE_DIR, 'uploads')
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(UPL_DIR, exist_ok=True)

ALLOWED_EXT = {'txt', 'docx', 'pdf'}

# ── Telegram API helpers ──────────────────────────────────────────────────────

def tg_get(method, params=None, timeout=15):
    url = f'{API}/{method}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(r.read())
    except Exception as e:
        print(f'[TG GET {method}] {e}')
        return {}

def tg_post(method, payload):
    data = json.dumps(payload).encode('utf-8')
    req  = urllib.request.Request(f'{API}/{method}', data=data,
                                   headers={'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return json.loads(r.read())
    except Exception as e:
        print(f'[TG POST {method}] {e}')
        return {}

def send_message(chat_id, text):
    tg_post('sendMessage', {'chat_id': chat_id, 'text': text})

def send_document(chat_id, path, caption=''):
    with open(path, 'rb') as f:
        data = f.read()
    boundary = b'----PDFBoundary'
    body = (
        b'--' + boundary + b'\r\n'
        b'Content-Disposition: form-data; name="chat_id"\r\n\r\n' +
        str(chat_id).encode() + b'\r\n'
        b'--' + boundary + b'\r\n'
        b'Content-Disposition: form-data; name="caption"\r\n\r\n' +
        caption.encode('utf-8') + b'\r\n'
        b'--' + boundary + b'\r\n'
        b'Content-Disposition: form-data; name="document"; filename="' +
        os.path.basename(path).encode() + b'"\r\n'
        b'Content-Type: application/pdf\r\n\r\n' +
        data + b'\r\n'
        b'--' + boundary + b'--\r\n'
    )
    req = urllib.request.Request(
        f'{API}/sendDocument', data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary.decode()}'}
    )
    try:
        urllib.request.urlopen(req, timeout=120)
    except Exception as e:
        print(f'[TG send_document] {e}')

def download_file(file_id, dest_path):
    info = tg_get('getFile', {'file_id': file_id})
    fpath = info.get('result', {}).get('file_path')
    if not fpath:
        raise RuntimeError('Could not get file path from Telegram')
    url = f'https://api.telegram.org/file/bot{TOKEN}/{fpath}'
    urllib.request.urlretrieve(url, dest_path)

# ── Pipeline worker ───────────────────────────────────────────────────────────

def detect_lang_from_text(text):
    try:
        from langdetect import detect
        code = detect(text[:3000])
        mapping = {'ru': 'Russian', 'en': 'English', 'uz': 'Uzbek'}
        return mapping.get(code, 'English')
    except Exception:
        return 'English'

def process_and_reply(chat_id, text, filename, language=None):
    sid = str(uuid.uuid4())[:8]
    try:
        send_message(chat_id, f'Qabul qilindi: {filename}\nAI ishlayapti, biroz kuting...')

        if not language:
            language = detect_lang_from_text(text)
            send_message(chat_id, f'Til aniqlandi: {language}')

        doc  = generate_pages(text, language=language)
        pp   = os.path.join(OUT_DIR, f'{sid}_presentation.pdf')
        mp   = os.path.join(OUT_DIR, f'{sid}_manuscript.pdf')
        build_presentation(doc, pp)
        build_manuscript(doc, mp)

        title = doc.get('title', filename)
        pages = len(doc.get('pages', []))
        send_message(chat_id, f'Tayyor! "{title}" — {pages} sahifa')
        send_document(chat_id, pp, f'Slaydlar: {title}')
        send_document(chat_id, mp, f'Suflyor: {title}')

    except Exception as e:
        tb = traceback.format_exc()
        print(f'[process_and_reply] {e}\n{tb}')
        send_message(chat_id, f'Xato yuz berdi: {e}')

# ── Message handler ───────────────────────────────────────────────────────────

def handle_message(msg):
    chat_id = msg['chat']['id']
    text_msg = msg.get('text', '')

    # /start or /help
    if text_msg.startswith('/start') or text_msg.startswith('/help'):
        send_message(chat_id,
            'PDF Pipeline Boti\n\n'
            'Menga quyidagilarni yuboring:\n'
            '- Matn (.txt, .docx, .pdf fayl)\n'
            '- Yoki oddiy xabar (tekst)\n\n'
            'Men sizga 2 ta PDF qaytaraman:\n'
            '1) Slaydlar (prezentatsiya)\n'
            '2) Suflyor (to\'liq matn)\n\n'
            'Til buyruqlari:\n'
            '/ru — Ruscha\n'
            '/uz — O\'zbekcha\n'
            '/en — Inglizcha'
        )
        return

    # Language override commands
    language = None
    if text_msg.startswith('/ru'):
        language = 'Russian'
        text_msg = text_msg[3:].strip()
    elif text_msg.startswith('/uz'):
        language = 'Uzbek'
        text_msg = text_msg[3:].strip()
    elif text_msg.startswith('/en'):
        language = 'English'
        text_msg = text_msg[3:].strip()

    # Document (file) received
    doc = msg.get('document')
    if doc:
        fname = doc.get('file_name', 'file')
        ext   = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
        if ext not in ALLOWED_EXT:
            send_message(chat_id, f'Faqat .txt .docx .pdf qabul qilinadi. Siz {ext} yubordingiz.')
            return
        sid      = str(uuid.uuid4())[:8]
        dest     = os.path.join(UPL_DIR, f'{sid}.{ext}')
        try:
            download_file(doc['file_id'], dest)
        except Exception as e:
            send_message(chat_id, f'Faylni yuklab bo\'lmadi: {e}')
            return
        try:
            raw_text = extract_text(dest, ext)
        except Exception as e:
            send_message(chat_id, f'Fayldan matn ajratib bo\'lmadi: {e}')
            return
        threading.Thread(
            target=process_and_reply,
            args=(chat_id, raw_text, fname, language),
            daemon=True
        ).start()
        return

    # Plain text message
    if text_msg and len(text_msg) > 30:
        threading.Thread(
            target=process_and_reply,
            args=(chat_id, text_msg, 'xabar', language),
            daemon=True
        ).start()
        return

    if text_msg and not text_msg.startswith('/'):
        send_message(chat_id, 'Matn juda qisqa. Kamida 30 ta belgi bo\'lsin yoki fayl yuboring.')

# ── Polling loop ──────────────────────────────────────────────────────────────

def main():
    print('Telegram bot ishga tushdi...')
    offset = 0
    while True:
        try:
            resp = tg_get('getUpdates', {'offset': offset, 'timeout': 10, 'limit': 10}, timeout=15)
            updates = resp.get('result', [])
            for upd in updates:
                offset = upd['update_id'] + 1
                msg = upd.get('message') or upd.get('edited_message')
                if msg:
                    try:
                        handle_message(msg)
                    except Exception as e:
                        print(f'[handle_message] {e}')
        except KeyboardInterrupt:
            print('Bot to\'xtatildi.')
            break
        except Exception as e:
            print(f'[polling] {e}')
            time.sleep(3)

if __name__ == '__main__':
    main()
