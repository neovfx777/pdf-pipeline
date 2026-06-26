"""
Telegram Downloads papkasidagi fayllarni pipeline orqali PDF ga aylantiradi
va Telegramga yuboradi.
"""
import os, sys, uuid, urllib.request, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import extract_text, generate_pages, build_presentation, build_manuscript, detect_language

TOKEN    = '8893623241:AAF2dQ8OsudZwiec7em5MdZIV9u-PScvU98'
CHAT_ID  = '8255330388'
API      = f'https://api.telegram.org/bot{TOKEN}'
OUT_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
TG_DIR   = r'C:\Users\neovf\Downloads\Telegram Desktop'

os.makedirs(OUT_DIR, exist_ok=True)

def send_message(text):
    data = json.dumps({'chat_id': CHAT_ID, 'text': text}).encode('utf-8')
    req  = urllib.request.Request(f'{API}/sendMessage', data=data,
                                   headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=15)

def send_document(path, caption=''):
    with open(path, 'rb') as f:
        data = f.read()
    boundary = b'----PDFBound'
    body = (
        b'--' + boundary + b'\r\n'
        b'Content-Disposition: form-data; name="chat_id"\r\n\r\n' +
        CHAT_ID.encode() + b'\r\n'
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
    urllib.request.urlopen(req, timeout=120)

def process_file(filepath, language='Uzbek'):
    filename = os.path.basename(filepath)
    ext = filename.rsplit('.', 1)[-1].lower()

    print(f'\n>>> {filename} qayta ishlanmoqda...')
    send_message(f'Qayta ishlanmoqda: {filename}\nBiroz kuting...')

    # Matn ajratish
    text = extract_text(filepath, ext)
    print(f'    Matn: {len(text)} belgi')

    # Til aniqlash
    lang_info = detect_language(text)
    detected  = lang_info.get('name', 'Unknown')
    print(f'    Aniqlangan til: {detected} → chiqish: {language}')

    # PDF yaratish
    print('    AI ishlayapti...')
    doc = generate_pages(text, language=language)
    title  = doc.get('title', filename)
    pages  = len(doc.get('pages', []))
    print(f'    Tayyor: "{title}" — {pages} sahifa')

    sid = str(uuid.uuid4())[:8]
    pp  = os.path.join(OUT_DIR, f'{sid}_presentation.pdf')
    mp  = os.path.join(OUT_DIR, f'{sid}_manuscript.pdf')
    build_presentation(doc, pp)
    build_manuscript(doc, mp)

    send_message(f'Tayyor! "{title}" — {pages} sahifa\nYuborilmoqda...')
    send_document(pp, f'Slaydlar: {title} [{language}]')
    send_document(mp, f'Suflyor: {title} [{language}]')
    print(f'    Telegramga yuborildi!')

# ── Qaysi fayllarni ishlash kerak ────────────────────────────────────────────
files_to_process = [
    (os.path.join(TG_DIR, '1 MAVZU.docx'), 'Uzbek'),
]

send_message(f'{len(files_to_process)} ta fayl topildi. PDF yaratish boshlanmoqda...')

for fpath, lang in files_to_process:
    if os.path.exists(fpath):
        try:
            process_file(fpath, lang)
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            print(f'XATO: {e}\n{err}')
            send_message(f'Xato: {os.path.basename(fpath)}\n{e}')
    else:
        print(f'Fayl topilmadi: {fpath}')

send_message('Barcha fayllar qayta ishlandi!')
print('\nHamma narsa tayyor.')
