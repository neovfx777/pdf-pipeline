"""
app.py — Flask server for PDF Pipeline
Run: python app.py → http://localhost:5050
"""

import os, uuid, json, traceback, threading, urllib.request, urllib.parse
from flask import Flask, request, jsonify, send_file, render_template
from pipeline import extract_text, generate_pages, revise_page, build_presentation, build_manuscript, calculate_pages, detect_language

TG_TOKEN   = '8893623241:AAF2dQ8OsudZwiec7em5MdZIV9u-PScvU98'
TG_CHAT_ID = '8255330388'
TG_API     = f'https://api.telegram.org/bot{TG_TOKEN}'

def tg_send_pdf(path, caption):
    """Send a PDF file to Telegram chat (non-blocking)."""
    def _send():
        try:
            with open(path, 'rb') as f:
                data = f.read()
            boundary = b'----TGBoundary'
            body = (
                b'--' + boundary + b'\r\n'
                b'Content-Disposition: form-data; name="chat_id"\r\n\r\n' +
                TG_CHAT_ID.encode() + b'\r\n'
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
                f'{TG_API}/sendDocument',
                data=body,
                headers={'Content-Type': f'multipart/form-data; boundary={boundary.decode()}'}
            )
            urllib.request.urlopen(req, timeout=60)
        except Exception as e:
            print(f'[Telegram] send failed: {e}')
    threading.Thread(target=_send, daemon=True).start()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

BASE  = os.path.dirname(os.path.abspath(__file__))
DIRS  = {k: os.path.join(BASE, k) for k in ('uploads','sessions','output')}
for d in DIRS.values(): os.makedirs(d, exist_ok=True)

ALLOWED = {'txt','docx','pdf'}

def spath(sid): return os.path.join(DIRS['sessions'], f'{sid}.json')
def ppath(sid): return os.path.join(DIRS['output'],   f'{sid}_presentation.pdf')
def mpath(sid): return os.path.join(DIRS['output'],   f'{sid}_manuscript.pdf')

def load(sid):
    p = spath(sid)
    if not os.path.exists(p): return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)

def save(sid, data):
    with open(spath(sid), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index(): return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files: return jsonify({'error':'No file'}), 400
    f   = request.files['file']
    ext = f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED: return jsonify({'error':f'Use: {", ".join(ALLOWED)}'}), 400
    sid = str(uuid.uuid4())[:8]
    fp  = os.path.join(DIRS['uploads'], f'{sid}.{ext}')
    f.save(fp)
    try:
        text = extract_text(fp, ext)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    lang = detect_language(text)
    save(sid, {'status':'uploaded', 'text':text, 'filename':f.filename})
    return jsonify({'session_id': sid, 'chars': len(text), 'filename': f.filename, 'est_pages': calculate_pages(text), 'detected_lang': lang})

@app.route('/text', methods=['POST'])
def text_input():
    """Accept raw pasted text."""
    body = request.get_json()
    text = (body.get('text') or '').strip()
    if not text: return jsonify({'error':'No text provided'}), 400
    sid = str(uuid.uuid4())[:8]
    lang = detect_language(text)
    save(sid, {'status':'uploaded', 'text':text, 'filename':'pasted text'})
    return jsonify({'session_id': sid, 'chars': len(text), 'filename': 'pasted text', 'est_pages': calculate_pages(text), 'detected_lang': lang})

@app.route('/generate', methods=['POST'])
def generate():
    body     = request.get_json()
    sid      = body.get('session_id')
    model    = body.get('model', 'mistral')
    language = body.get('language', 'English')
    sess     = load(sid)
    if not sess: return jsonify({'error':'Session not found'}), 404
    text = sess.get('text','')
    if not text: return jsonify({'error':'No text'}), 400
    try:
        doc = generate_pages(text, model=model, language=language)
        build_presentation(doc, ppath(sid))
        build_manuscript(doc, mpath(sid))
    except Exception as e:
        tb = traceback.format_exc()
        app.logger.error(tb)
        return jsonify({'error': str(e), 'detail': tb}), 500
    sess.update({'status':'generated', 'doc_data': doc})
    save(sid, sess)
    doc_title = doc.get('title', sid)
    tg_send_pdf(ppath(sid), f'Slaydlar: {doc_title} ({language})')
    tg_send_pdf(mpath(sid), f'Suflyor: {doc_title} ({language})')
    return jsonify({'session_id':sid, 'title':doc_title, 'pages':len(doc['pages'])})

@app.route('/session/<sid>')
def get_session(sid):
    sess = load(sid)
    if not sess: return jsonify({'error':'Not found'}), 404
    doc = sess.get('doc_data', {})
    return jsonify({'title': doc.get('title',''), 'pages': doc.get('pages',[])})

@app.route('/preview/presentation/<sid>')
def preview_pres(sid):
    p = ppath(sid)
    if not os.path.exists(p): return 'Not found', 404
    return send_file(p, mimetype='application/pdf')

@app.route('/preview/manuscript/<sid>')
def preview_manu(sid):
    p = mpath(sid)
    if not os.path.exists(p): return 'Not found', 404
    return send_file(p, mimetype='application/pdf')

@app.route('/download/presentation/<sid>')
def dl_pres(sid):
    sess = load(sid); p = ppath(sid)
    if not os.path.exists(p): return 'Not found', 404
    title = (sess or {}).get('doc_data',{}).get('title','presentation')
    name  = ''.join(c for c in title if c.isalnum() or c in ' _-')[:40].strip()
    return send_file(p, as_attachment=True, download_name=f'{name}_slides.pdf')

@app.route('/download/manuscript/<sid>')
def dl_manu(sid):
    sess = load(sid); p = mpath(sid)
    if not os.path.exists(p): return 'Not found', 404
    title = (sess or {}).get('doc_data',{}).get('title','manuscript')
    name  = ''.join(c for c in title if c.isalnum() or c in ' _-')[:40].strip()
    return send_file(p, as_attachment=True, download_name=f'{name}_manuscript.pdf')

@app.route('/revise', methods=['POST'])
def revise():
    body = request.get_json()
    try:
        page_num = int(body.get('page_num', 1))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid page_num'}), 400
    sid        = body.get('session_id')
    instruction= body.get('instruction', '')
    model      = body.get('model', 'mistral')
    language   = body.get('language', 'English')
    sess = load(sid)
    if not sess or 'doc_data' not in sess: return jsonify({'error':'Not found'}), 404
    doc   = sess['doc_data']
    pages = doc['pages']
    idx   = next((i for i,p in enumerate(pages) if p.get('page_num')==page_num), None)
    if idx is None: return jsonify({'error':f'Page {page_num} not found'}), 404
    try:
        revised = revise_page(pages[idx], instruction, model=model, language=language)
        pages[idx] = revised
        build_presentation(doc, ppath(sid))
        build_manuscript(doc, mpath(sid))
    except Exception as e:
        tb = traceback.format_exc()
        app.logger.error(tb)
        return jsonify({'error': str(e), 'detail': tb}), 500
    sess['doc_data'] = doc
    save(sid, sess)
    doc_title = doc.get('title', sid)
    tg_send_pdf(ppath(sid), f'Slaydlar (yangilangan): {doc_title} ({language})')
    tg_send_pdf(mpath(sid), f'Suflyor (yangilangan): {doc_title} ({language})')
    return jsonify({'success':True, 'page': revised})

if __name__ == '__main__':
    print('\nPDF Pipeline -> http://localhost:5050\n')
    app.run(host='0.0.0.0', port=5050, debug=False)
