import os
import json
import time
import uuid
import traceback
from functools import wraps
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ---- Request tracing: log every incoming API call and its response status ----
@app.before_request
def _trace_request_in():
    if request.path.startswith('/api/'):
        auth = request.headers.get('Authorization', '')
        has_token = 'yes' if auth.startswith('Bearer ') else 'no'
        print(f"[REQ→] {request.method} {request.path}  token={has_token}", flush=True)

@app.after_request
def _trace_request_out(response):
    if request.path.startswith('/api/'):
        print(f"[REQ←] {request.method} {request.path}  status={response.status_code}", flush=True)
    return response

VALID_TOKENS = {}

SHEET_ID = '1J3t28M_0oZuVjkZ8GxNrD08kiGqd-A08I23jAiv8dPU'
SHEET_NAME = 'Base'

# Column indices (1-indexed for gspread, 0-indexed for list access)
COL_FOLIO    = 2   # B
COL_FECHA    = 3   # C
COL_EJECUTIVO= 4   # D
COL_PRODUCTO = 5   # E
COL_CARACT   = 6   # F
COL_LADO     = 7   # G
COL_VEHICULO = 8   # H

# Ignacio — La Reina
COL_IGNACIO_STATUS = 11  # K
COL_IGNACIO_RESP   = 12  # L

# Robinson — Externo
COL_ROBINSON_STATUS = 13  # M
COL_ROBINSON_RESP   = 14  # N

# Shared
COL_LINK = 15  # O
COLS_FOTOS = [16, 17, 18, 19, 20, 21]  # P, Q, R, S, T, U

# Client data (filled in by callcenter when creating a new consultation)
COL_CLIENTE_NOMBRE    = 22  # V
COL_CLIENTE_TELEFONO  = 23  # W
COL_CLIENTE_EMAIL     = 24  # X

USER_CONFIG = {
    'ignacio': {
        'display_name': 'Ignacio Castañeda',
        'status_col':      COL_IGNACIO_STATUS,
        'resp_col':        COL_IGNACIO_RESP,
        'other_name':      'Robinson',
        'other_status_col': COL_ROBINSON_STATUS,
        'other_resp_col':   COL_ROBINSON_RESP,
    },
    'robinson': {
        'display_name': 'Robinson',
        'status_col':      COL_ROBINSON_STATUS,
        'resp_col':        COL_ROBINSON_RESP,
        'other_name':      'Ignacio',
        'other_status_col': COL_IGNACIO_STATUS,
        'other_resp_col':   COL_IGNACIO_RESP,
    },
}

# ---- In-memory foto event log ----
recent_foto_events = []
recent_resp_events = []

def get_gspread_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    if os.path.exists('credentials.json'):
        creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    elif os.environ.get('GOOGLE_CREDENTIALS_JSON'):
        creds_dict = json.loads(os.environ.get('GOOGLE_CREDENTIALS_JSON'))
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        raise Exception("No se encontraron credenciales de Google.")
    return gspread.authorize(creds)

def compute_user_key(name, role):
    """Decide which user_key a row maps to.
    Priority: explicit Rol column values set via admin UI > legacy name matching.
    """
    role_l = (role or '').lower().strip()
    name_l = (name or '').lower().strip()
    # Explicit roles assigned via admin UI
    if role_l == 'respuesta-ignacio':  return 'ignacio'
    if role_l == 'respuesta-robinson': return 'robinson'
    if role_l == 'consulta':           return 'callcenter'
    # Legacy fallback: infer from the user's name
    if 'ignacio'  in name_l: return 'ignacio'
    if 'robinson' in name_l: return 'robinson'
    return 'callcenter'

def get_user_from_token(token):
    if not token:
        print("[AUTH] get_user_from_token: token vacío", flush=True)
        return None
    token = token.strip()
    if not token:
        print("[AUTH] get_user_from_token: token sólo espacios", flush=True)
        return None
    if token in VALID_TOKENS:
        return VALID_TOKENS[token]
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet('Usuarios')
        rows = sheet.get_all_values()
        print(f"[AUTH] Buscando token (len={len(token)}) entre {len(rows)-1} usuarios en la hoja 'Usuarios'", flush=True)
        for r in rows[1:]:
            if len(r) < 6:
                continue
            sheet_token  = (r[5] or '').strip()
            sheet_estado = (r[3] or '').strip()
            if sheet_token == token and sheet_estado == 'Aprobado':
                user = {
                    'email':    (r[0] or '').strip(),
                    'name':     (r[1] or '').strip(),
                    'role':     (r[2] or '').strip(),
                    'user_key': compute_user_key(r[1] if len(r) > 1 else '',
                                                 r[2] if len(r) > 2 else ''),
                }
                VALID_TOKENS[token] = user
                print(f"[AUTH] ✅ Token válido para {user['email']} ({user['user_key']})", flush=True)
                return user
        print(f"[AUTH] ❌ Token no coincide con ninguna fila Aprobada. Primeros 8 chars del token recibido: {token[:8]}…", flush=True)
    except Exception as e:
        print(f"[AUTH ERROR] get_user_from_token explotó: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
    return None

def safe_get(row, col_1indexed):
    idx = col_1indexed - 1
    if idx < len(row):
        return row[idx].strip()
    return ''

@app.route('/')
def index():
    imgbb_key = os.environ.get('IMGBB_API_KEY', '')
    return render_template('index.html', imgbb_key=imgbb_key)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '') or ''
        auth_header = auth_header.strip()
        if not auth_header.lower().startswith('bearer '):
            print(f"[AUTH] ❌ Header Authorization inválido: {auth_header[:20]!r} en {request.path}", flush=True)
            return jsonify({'error': 'Acceso no autorizado'}), 401
        token = auth_header[7:].strip()
        user_obj = get_user_from_token(token)
        if not user_obj:
            print(f"[AUTH] ❌ Token rechazado en {request.path}", flush=True)
            return jsonify({'error': 'Sesión expirada o inválida'}), 401

        # Inject user logic inside the request context
        request.user_obj = user_obj
        return f(*args, **kwargs)
    return decorated

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')
    if not email or not password:
        return jsonify({'error': 'Faltan credenciales'}), 400
    try:
        client = get_gspread_client()
        try:
            sheet = client.open_by_key(SHEET_ID).worksheet('Usuarios')
        except gspread.exceptions.WorksheetNotFound:
            return jsonify({'error': 'La hoja Usuarios no existe'}), 500
        rows = sheet.get_all_values()
        for idx, r in enumerate(rows[1:], start=2):
            if len(r) > 0 and r[0].lower() == email:
                if len(r) < 6: r += [''] * (6 - len(r))
                estado, p_hash = r[3], r[4]
                if estado != 'Aprobado':
                    return jsonify({'error': 'Usuario en espera de aprobación.'}), 403
                if check_password_hash(p_hash, password):
                    token = str(uuid.uuid4()).strip()
                    sheet.update_cell(idx, 6, token)
                    print(f"[AUTH] Nuevo token emitido para {email} → {token[:8]}…", flush=True)
                    user_key = compute_user_key(r[1], r[2])
                    
                    user_obj = {'email': email, 'name': r[1], 'role': r[2], 'user_key': user_key}
                    VALID_TOKENS[token] = user_obj
                    return jsonify({'token': token, 'user': user_obj})
                else:
                    return jsonify({'error': 'Contraseña incorrecta'}), 401
        return jsonify({'error': 'Usuario no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    email = data.get('email', '').strip().lower()
    name = data.get('name', '').strip()
    password = data.get('password', '')
    if not email or not name or not password:
        return jsonify({'error': 'Datos incompletos'}), 400
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet('Usuarios')
        for r in sheet.get_all_values()[1:]:
            if len(r) > 0 and r[0].lower() == email:
                return jsonify({'error': 'Correo ya registrado'}), 400
        
        sheet.append_row([email, name, 'Ingreso de consultas', 'Pendiente', generate_password_hash(password, method="pbkdf2:sha256"), ''])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pending', methods=['GET'])
@require_auth
def get_pending():
    try:
        user = request.args.get('user', '').lower()
        if not user:
            user = request.user_obj.get('user_key', '')
        if user not in USER_CONFIG:
            return jsonify({"error": "Usuario no válido. Usa ?user=ignacio o ?user=robinson"}), 400

        cfg = USER_CONFIG[user]
        sc  = cfg['status_col']
        rc  = cfg['resp_col']
        osc = cfg['other_status_col']
        orc = cfg['other_resp_col']
        max_col = max(sc, rc, osc, orc)

        client = get_gspread_client()
        sheet  = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        all_rows = sheet.get_all_values()

        data_rows = all_rows[1:]  # skip header

        pending = []
        answered_cache = {}

        for idx, row in enumerate(data_rows, start=2):
            # Pad if necessary
            if len(row) < max_col:
                row = row + [''] * (max_col - len(row))

            my_status   = safe_get(row, sc)
            my_resp     = safe_get(row, rc)
            other_status= safe_get(row, osc)
            other_resp  = safe_get(row, orc)
            producto    = safe_get(row, COL_PRODUCTO)
            vehiculo    = safe_get(row, COL_VEHICULO)

            # A question is only valid if D, E, G, and H are complete
            is_valid = bool(
                safe_get(row, COL_EJECUTIVO).strip() and
                safe_get(row, COL_PRODUCTO).strip() and
                safe_get(row, COL_LADO).strip() and
                safe_get(row, COL_VEHICULO).strip()
            )

            # Already answered by me → skip but cache for duplicate detection
            if my_status or my_resp:
                key = (producto.lower(), vehiculo.lower())
                answered_cache.setdefault(key, []).append({
                    "row": idx,
                    "response": f"{my_status} — {my_resp}".strip(" —")
                })
                continue

            # Pending for me
            if not my_status and not my_resp and is_valid:
                pending.append({
                    "row_index":      idx,
                    "folio":          safe_get(row, COL_FOLIO),
                    "fecha":          safe_get(row, COL_FECHA),
                    "ejecutivo":      safe_get(row, COL_EJECUTIVO),
                    "producto":       producto,
                    "caracteristicas":safe_get(row, COL_CARACT),
                    "lado":           safe_get(row, COL_LADO),
                    "marca_modelo_año": vehiculo,
                    "fotos":          [safe_get(row, c) for c in COLS_FOTOS],
                    "link":           safe_get(row, COL_LINK),
                    "other_user":     cfg['other_name'],
                    "other_status":   other_status,
                    "other_resp":     other_resp,
                    "cliente_nombre":   safe_get(row, COL_CLIENTE_NOMBRE),
                    "cliente_telefono": safe_get(row, COL_CLIENTE_TELEFONO),
                    "cliente_email":    safe_get(row, COL_CLIENTE_EMAIL),
                    "duplicates":     []
                })

        # Inject duplicate info
        for p in pending:
            key = (p["producto"].lower(), p["marca_modelo_año"].lower())
            if key in answered_cache:
                p["duplicates"] = answered_cache[key]

        return jsonify(pending)

    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/history', methods=['GET'])
@require_auth
def get_history():
    try:
        user = request.args.get('user', '').lower()
        if not user:
            user = request.user_obj.get('user_key', '')
        if user not in USER_CONFIG:
            return jsonify({"error": "Usuario no válido"}), 400

        cfg = USER_CONFIG[user]
        sc  = cfg['status_col']
        rc  = cfg['resp_col']
        osc = cfg['other_status_col']
        orc = cfg['other_resp_col']
        max_col = max(sc, rc, osc, orc, COL_LINK, max(COLS_FOTOS), COL_CLIENTE_EMAIL)

        client = get_gspread_client()
        sheet  = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        all_rows = sheet.get_all_values()

        data_rows = all_rows[1:]
        history = []

        for idx, row in enumerate(data_rows, start=2):
            if len(row) < max_col:
                row = row + [''] * (max_col - len(row))

            my_status = safe_get(row, sc)
            my_resp   = safe_get(row, rc)
            producto  = safe_get(row, COL_PRODUCTO)

            is_valid = bool(
                safe_get(row, COL_EJECUTIVO).strip() and
                safe_get(row, COL_PRODUCTO).strip() and
                safe_get(row, COL_LADO).strip() and
                safe_get(row, COL_VEHICULO).strip()
            )

            # Only rows I have answered
            if (my_status or my_resp) and is_valid:
                history.append({
                    "row_index":        idx,
                    "folio":            safe_get(row, COL_FOLIO),
                    "fecha":            safe_get(row, COL_FECHA),
                    "ejecutivo":        safe_get(row, COL_EJECUTIVO),
                    "producto":         producto,
                    "caracteristicas":  safe_get(row, COL_CARACT),
                    "lado":             safe_get(row, COL_LADO),
                    "marca_modelo_año": safe_get(row, COL_VEHICULO),
                    "my_status":        my_status,
                    "my_resp":          my_resp,
                    "fotos":            [safe_get(row, c) for c in COLS_FOTOS],
                    "link":             safe_get(row, COL_LINK),
                    "other_user":       cfg['other_name'],
                    "other_status":     safe_get(row, osc),
                    "other_resp":       safe_get(row, orc),
                    "cliente_nombre":   safe_get(row, COL_CLIENTE_NOMBRE),
                    "cliente_telefono": safe_get(row, COL_CLIENTE_TELEFONO),
                    "cliente_email":    safe_get(row, COL_CLIENTE_EMAIL),
                })

        # Most recent first (highest row index = bottom of sheet = newest)
        history.reverse()
        return jsonify(history)

    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/consultations', methods=['GET'])
@require_auth
def consultations():
    try:
        q = request.args.get('q', '').strip().lower()
        if len(q) < 2:
            return jsonify([])

        client = get_gspread_client()
        sheet  = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        all_rows = sheet.get_all_values()

        # Split into tokens so "toyota parabrisas" matches rows that have both
        tokens = [t for t in q.split() if t]

        results = []
        for idx, row in enumerate(all_rows[1:], start=2):
            padded = row + [''] * 30
            folio    = safe_get(padded, COL_FOLIO)
            producto = safe_get(padded, COL_PRODUCTO)
            vehiculo = safe_get(padded, COL_VEHICULO)
            ejecutivo= safe_get(padded, COL_EJECUTIVO)

            is_valid = bool(
                safe_get(padded, COL_EJECUTIVO).strip() and
                safe_get(padded, COL_PRODUCTO).strip() and
                safe_get(padded, COL_LADO).strip() and
                safe_get(padded, COL_VEHICULO).strip()
            )

            if not is_valid:
                continue

            # Build a single searchable string from every meaningful field
            searchable = ' '.join([
                folio,
                producto,
                safe_get(padded, COL_CARACT),
                safe_get(padded, COL_LADO),
                vehiculo,
                ejecutivo,
                safe_get(padded, COL_CLIENTE_NOMBRE),
                safe_get(padded, COL_CLIENTE_TELEFONO),
                safe_get(padded, COL_CLIENTE_EMAIL),
            ]).lower()

            # Every token must appear somewhere in the searchable string
            if not all(t in searchable for t in tokens):
                continue

            results.append({
                'row_index':        idx,
                'folio':            folio,
                'fecha':            safe_get(padded, COL_FECHA),
                'ejecutivo':        ejecutivo,
                'producto':         producto,
                'caracteristicas':  safe_get(padded, COL_CARACT),
                'lado':             safe_get(padded, COL_LADO),
                'marca_modelo_año': vehiculo,
                'fotos':            [safe_get(padded, c) for c in COLS_FOTOS],
                'la_reina':         safe_get(padded, COL_IGNACIO_STATUS),
                'la_reina_resp':    safe_get(padded, COL_IGNACIO_RESP),
                'externo':          safe_get(padded, COL_ROBINSON_STATUS),
                'robinson_resp':    safe_get(padded, COL_ROBINSON_RESP),
                'cliente_nombre':   safe_get(padded, COL_CLIENTE_NOMBRE),
                'cliente_telefono': safe_get(padded, COL_CLIENTE_TELEFONO),
                'cliente_email':    safe_get(padded, COL_CLIENTE_EMAIL),
            })
            if len(results) >= 20:
                break

        return jsonify(results)
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/update-consultation', methods=['POST'])
@require_auth
def update_consultation():
    """Callcenter (or admin) can edit the main fields of an existing consultation."""
    try:
        user = get_user_from_token(request.headers.get('Authorization','').replace('Bearer ','').strip())
        if user.get('user_key') not in ('callcenter', 'robinson'):
            return jsonify({'error': 'Sin permiso'}), 403

        data      = request.json
        row_idx   = int(data.get('row_index', 0))
        if row_idx < 2:
            return jsonify({'error': 'row_index inválido'}), 400

        producto  = data.get('producto',         '').strip()
        vehiculo  = data.get('vehiculo',          '').strip()
        lado      = data.get('lado',              '').strip()
        caract    = data.get('caracteristicas',   '').strip()
        cli_nombre= data.get('cliente_nombre',    '').strip()
        cli_tel   = data.get('cliente_telefono',  '').strip()
        cli_email = data.get('cliente_email',     '').strip()

        if not producto or not vehiculo or not lado:
            return jsonify({'error': 'Producto, vehículo y lado son obligatorios'}), 400

        client = get_gspread_client()
        sheet  = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

        # Batch-update only the editable columns
        updates = [
            (row_idx, COL_PRODUCTO,         producto),
            (row_idx, COL_CARACT,           caract),
            (row_idx, COL_LADO,             lado),
            (row_idx, COL_VEHICULO,         vehiculo),
            (row_idx, COL_CLIENTE_NOMBRE,   cli_nombre),
            (row_idx, COL_CLIENTE_TELEFONO, cli_tel),
            (row_idx, COL_CLIENTE_EMAIL,    cli_email),
        ]
        for r, c, v in updates:
            sheet.update_cell(r, c, v)

        print(f"[CC-EDIT] row={row_idx} folio actualizado", flush=True)
        return jsonify({'ok': True})
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/update-foto', methods=['POST'])
@require_auth
def update_foto():
    try:
        data    = request.json
        row_idx = data.get('row_index')
        url     = data.get('foto_url', '')
        folio   = data.get('folio', '')
        producto= data.get('producto', '')
        foto_idx= data.get('foto_index', None) # 0 to 5 if deleting

        client = get_gspread_client()
        sheet  = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

        if url == '' and foto_idx is not None:
            # We are deleting a specific photo
            target_col = COLS_FOTOS[int(foto_idx)]
            sheet.update_cell(row_idx, target_col, '')
        else:
            # We are adding a photo, find the first empty column
            row_data = sheet.row_values(row_idx)
            # pad to at least 21 items to avoid index errors
            padded = row_data + [''] * max(0, 22 - len(row_data))
            
            target_col = None
            for c in COLS_FOTOS:
                if not safe_get(padded, c):
                    target_col = c
                    break
            
            if not target_col:
                return jsonify({'error': 'Límite de 6 fotos alcanzado.'}), 400
                
            sheet.update_cell(row_idx, target_col, url)
            
            # Clear user statuses so the folio goes back to Pending for both
            sheet.update_cell(row_idx, COL_IGNACIO_STATUS, '')
            sheet.update_cell(row_idx, COL_IGNACIO_RESP, '')
            sheet.update_cell(row_idx, COL_ROBINSON_STATUS, '')
            sheet.update_cell(row_idx, COL_ROBINSON_RESP, '')

        # Record event so respondents can be notified
        recent_foto_events.append({
            'folio':    folio,
            'producto': producto,
            'url':      url,
            'ts':       time.time(),
        })
        # Keep only the last 30 events
        if len(recent_foto_events) > 30:
            recent_foto_events.pop(0)

        return jsonify({'success': True})
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/foto-events', methods=['GET'])
@require_auth
def foto_events():
    since = request.args.get('since', type=int, default=0)
    new_events = [e for e in recent_foto_events if e['ts'] > since]
    return jsonify(new_events)


@app.route('/api/resp-events', methods=['GET'])
@require_auth
def resp_events():
    since = request.args.get('since', type=int, default=0)
    new_events = [e for e in recent_resp_events if e['ts'] > since]
    return jsonify(new_events)


@app.route('/api/recent-folios', methods=['GET'])
@require_auth
def recent_folios():
    try:
        client   = get_gspread_client()
        sheet    = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        all_rows = sheet.get_all_values()
        data_rows = all_rows[1:]  # skip header

        results = []
        for raw_idx, row in enumerate(reversed(data_rows)):
            actual_idx = len(data_rows) - raw_idx + 1  # 1-based row in sheet
            padded = row + [''] * 30
            folio = safe_get(padded, COL_FOLIO)
            
            is_valid = bool(
                safe_get(padded, COL_EJECUTIVO).strip() and
                safe_get(padded, COL_PRODUCTO).strip() and
                safe_get(padded, COL_LADO).strip() and
                safe_get(padded, COL_VEHICULO).strip()
            )

            if not is_valid:
                continue
                
            results.append({
                'row_index':        actual_idx,
                'folio':            folio,
                'fecha':            safe_get(padded, COL_FECHA),
                'ejecutivo':        safe_get(padded, COL_EJECUTIVO),
                'producto':         safe_get(padded, COL_PRODUCTO),
                'caracteristicas':  safe_get(padded, COL_CARACT),
                'lado':             safe_get(padded, COL_LADO),
                'marca_modelo_año': safe_get(padded, COL_VEHICULO),
                'fotos':            [safe_get(padded, c) for c in COLS_FOTOS],
                'la_reina':         safe_get(padded, COL_IGNACIO_STATUS),
                'la_reina_resp':    safe_get(padded, COL_IGNACIO_RESP),
                'externo':          safe_get(padded, COL_ROBINSON_STATUS),
                'robinson_resp':    safe_get(padded, COL_ROBINSON_RESP),
                'cliente_nombre':   safe_get(padded, COL_CLIENTE_NOMBRE),
                'cliente_telefono': safe_get(padded, COL_CLIENTE_TELEFONO),
                'cliente_email':    safe_get(padded, COL_CLIENTE_EMAIL),
            })
            if len(results) >= 18:
                break

        return jsonify(results)
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/update', methods=['POST'])
@require_auth
def update_row():
    try:
        data         = request.json
        row_idx      = data.get('row_index')
        status       = data.get('status', '')
        response_text= data.get('response', '')
        link         = data.get('link', '')
        
        user         = data.get('user', '').lower()
        if not user:
            user = request.user_obj.get('user_key', '')

        if user not in USER_CONFIG:
            return jsonify({"error": "Usuario no válido"}), 400

        cfg = USER_CONFIG[user]

        client = get_gspread_client()
        sheet  = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

        sheet.update_cell(row_idx, cfg['status_col'], status)
        sheet.update_cell(row_idx, cfg['resp_col'], response_text)
        if link:
            sheet.update_cell(row_idx, COL_LINK, link)

        folio = data.get('folio', '')
        if folio:
            recent_resp_events.append({
                'ts': time.time(),
                'folio': folio,
                'user': cfg['display_name'],
                'status': status
            })
            if len(recent_resp_events) > 50:
                recent_resp_events.pop(0)

        return jsonify({"success": True})

    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({"error": str(e)}), 500


# =============================================
# NEW CONSULTATION CREATION (callcenter only)
# =============================================
def compute_next_folio(sheet):
    """Scan column B of the Base sheet and return max(numeric folios) + 1.
    Falls back to 1 if no numeric folio is found yet.
    """
    try:
        col_values = sheet.col_values(COL_FOLIO)  # list of strings, includes header
        max_folio = 0
        for v in col_values[1:]:  # skip header
            if not v:
                continue
            # Allow folios that are pure integers OR ones with non-digit prefix/suffix
            # by extracting the longest digit run.
            digits = ''
            for ch in str(v):
                if ch.isdigit():
                    digits += ch
                elif digits:
                    break
            if digits:
                try:
                    n = int(digits)
                    if n > max_folio:
                        max_folio = n
                except ValueError:
                    pass
        return max_folio + 1
    except Exception as e:
        print(f"[FOLIO] compute_next_folio falló, fallback a timestamp: {e}", flush=True)
        return int(time.time())


@app.route('/api/new-consultation', methods=['POST'])
@require_auth
def new_consultation():
    """Create a new row in the Base sheet from the callcenter form.
    Only users with user_key='callcenter' may use this endpoint.
    """
    try:
        user_obj = request.user_obj
        # Callcenter normal flow + Robinson (admin) so he can preview/test the screen.
        if user_obj.get('user_key') not in ('callcenter', 'robinson'):
            return jsonify({'error': 'Solo el call center puede crear consultas nuevas.'}), 403

        data = request.json or {}
        producto       = (data.get('producto', '') or '').strip()
        caracteristicas= (data.get('caracteristicas', '') or '').strip()
        lado           = (data.get('lado', '') or '').strip()
        vehiculo       = (data.get('vehiculo', '') or '').strip()
        cliente_nombre = (data.get('cliente_nombre', '') or '').strip()
        cliente_tel    = (data.get('cliente_telefono', '') or '').strip()
        cliente_email  = (data.get('cliente_email', '') or '').strip()

        # Required fields
        missing = []
        if not producto: missing.append('producto')
        if not lado:     missing.append('lado')
        if not vehiculo: missing.append('vehiculo')
        if missing:
            return jsonify({'error': f'Faltan campos obligatorios: {", ".join(missing)}'}), 400

        client = get_gspread_client()
        sheet  = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

        folio = compute_next_folio(sheet)
        fecha = time.strftime('%d/%m/%Y')
        ejecutivo = user_obj.get('name', '') or 'Call Center'

        # Build a row that lines up with the existing columns.
        # Columns: A(empty), B=Folio, C=Fecha, D=Ejecutivo, E=Producto, F=Caract,
        # G=Lado, H=Vehiculo, I-J(empty), K-L(ignacio), M-N(robinson),
        # O=Link, P-U=Fotos, V=Cliente Nombre, W=Cliente Tel, X=Cliente Email
        row = [''] * COL_CLIENTE_EMAIL
        row[COL_FOLIO - 1]            = str(folio)
        row[COL_FECHA - 1]            = fecha
        row[COL_EJECUTIVO - 1]        = ejecutivo
        row[COL_PRODUCTO - 1]         = producto
        row[COL_CARACT - 1]           = caracteristicas
        row[COL_LADO - 1]             = lado
        row[COL_VEHICULO - 1]         = vehiculo
        row[COL_CLIENTE_NOMBRE - 1]   = cliente_nombre
        row[COL_CLIENTE_TELEFONO - 1] = cliente_tel
        row[COL_CLIENTE_EMAIL - 1]    = cliente_email

        sheet.append_row(row, value_input_option='USER_ENTERED')
        # gspread doesn't return the row index from append_row in older versions,
        # so we infer it from the current row count.
        new_row_idx = len(sheet.col_values(COL_FOLIO))

        print(f"[NEW] Folio {folio} creado por {ejecutivo} en fila {new_row_idx}", flush=True)
        return jsonify({
            'success':   True,
            'folio':     folio,
            'row_index': new_row_idx,
            'fecha':     fecha,
            'ejecutivo': ejecutivo,
        })

    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': str(e)}), 500


# =============================================
# USER MANAGEMENT (admin-only, Robinson)
# =============================================
def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = (request.headers.get('Authorization', '') or '').strip()
        if not auth_header.lower().startswith('bearer '):
            return jsonify({'error': 'Acceso no autorizado'}), 401
        token = auth_header[7:].strip()
        user_obj = get_user_from_token(token)
        if not user_obj:
            return jsonify({'error': 'Sesión expirada o inválida'}), 401
        if user_obj.get('user_key') != 'robinson':
            print(f"[ADMIN] ❌ Acceso denegado a {user_obj.get('email')} ({user_obj.get('user_key')})", flush=True)
            return jsonify({'error': 'Solo el administrador puede acceder'}), 403
        request.user_obj = user_obj
        return f(*args, **kwargs)
    return decorated


@app.route('/api/users', methods=['GET'])
@require_admin
def list_users():
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet('Usuarios')
        rows = sheet.get_all_values()
        users = []
        for idx, r in enumerate(rows[1:], start=2):
            if not r or not (r[0] or '').strip():
                continue
            padded = r + [''] * max(0, 6 - len(r))
            users.append({
                'row_index': idx,
                'email':     (padded[0] or '').strip(),
                'name':      (padded[1] or '').strip(),
                'role':      (padded[2] or '').strip(),
                'estado':    (padded[3] or '').strip(),
                'has_token': bool((padded[5] or '').strip()),
                'user_key':  compute_user_key(padded[1], padded[2]),
            })
        return jsonify(users)
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/users/approve', methods=['POST'])
@require_admin
def approve_user():
    try:
        data = request.json or {}
        row_idx = int(data.get('row_index', 0))
        if row_idx < 2:
            return jsonify({'error': 'row_index inválido'}), 400
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet('Usuarios')
        sheet.update_cell(row_idx, 4, 'Aprobado')  # col D = Estado
        print(f"[ADMIN] ✅ Usuario en fila {row_idx} aprobado", flush=True)
        return jsonify({'success': True})
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': str(e)}), 500


ALLOWED_ROLES = {'Consulta', 'Respuesta-Ignacio', 'Respuesta-Robinson'}

@app.route('/api/users/role', methods=['POST'])
@require_admin
def set_user_role():
    try:
        data = request.json or {}
        row_idx = int(data.get('row_index', 0))
        new_role = (data.get('role', '') or '').strip()
        if row_idx < 2:
            return jsonify({'error': 'row_index inválido'}), 400
        if new_role not in ALLOWED_ROLES:
            return jsonify({'error': f'Rol inválido. Usa uno de: {sorted(ALLOWED_ROLES)}'}), 400
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet('Usuarios')
        sheet.update_cell(row_idx, 3, new_role)  # col C = Rol
        # Clear in-memory token cache so the new role takes effect on the next request
        VALID_TOKENS.clear()
        print(f"[ADMIN] 🔄 Rol de fila {row_idx} cambiado a {new_role}", flush=True)
        return jsonify({'success': True})
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/users/revoke', methods=['POST'])
@require_admin
def revoke_user():
    try:
        data = request.json or {}
        row_idx = int(data.get('row_index', 0))
        if row_idx < 2:
            return jsonify({'error': 'row_index inválido'}), 400
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet('Usuarios')
        sheet.update_cell(row_idx, 4, 'Revocado')  # col D = Estado
        sheet.update_cell(row_idx, 6, '')          # col F = Token
        VALID_TOKENS.clear()
        print(f"[ADMIN] 🚫 Usuario en fila {row_idx} revocado", flush=True)
        return jsonify({'success': True})
    except Exception as e:
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
