import os
import json
import time
import traceback
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

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

def safe_get(row, col_1indexed):
    idx = col_1indexed - 1
    if idx < len(row):
        return row[idx].strip()
    return ''

@app.route('/')
def index():
    imgbb_key = os.environ.get('IMGBB_API_KEY', '')
    return render_template('index.html', imgbb_key=imgbb_key)

@app.route('/api/pending', methods=['GET'])
def get_pending():
    try:
        user = request.args.get('user', '').lower()
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
                    "duplicates":     []
                })

        # Inject duplicate info
        for p in pending:
            key = (p["producto"].lower(), p["marca_modelo_año"].lower())
            if key in answered_cache:
                p["duplicates"] = answered_cache[key]

        return jsonify(pending)

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        user = request.args.get('user', '').lower()
        if user not in USER_CONFIG:
            return jsonify({"error": "Usuario no válido"}), 400

        cfg = USER_CONFIG[user]
        sc  = cfg['status_col']
        rc  = cfg['resp_col']
        osc = cfg['other_status_col']
        orc = cfg['other_resp_col']
        max_col = max(sc, rc, osc, orc, COL_LINK, max(COLS_FOTOS))

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
                })

        # Most recent first (highest row index = bottom of sheet = newest)
        history.reverse()
        return jsonify(history[:200])  # cap at 200 items

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/api/consultations', methods=['GET'])
def search_consultations():
    try:
        q = request.args.get('q', '').strip().lower()
        if len(q) < 2:
            return jsonify([])

        client = get_gspread_client()
        sheet  = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        all_rows = sheet.get_all_values()

        results = []
        for idx, row in enumerate(all_rows[1:], start=2):
            padded = row + [''] * 25
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

            if not (q in folio.lower() or q in producto.lower()
                    or q in vehiculo.lower() or q in ejecutivo.lower()):
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
            })
            if len(results) >= 20:
                break

        return jsonify(results)
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/update-foto', methods=['POST'])
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
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/foto-events', methods=['GET'])
def foto_events():
    since = request.args.get('since', type=int, default=0)
    new_events = [e for e in recent_foto_events if e['ts'] > since]
    return jsonify(new_events)


@app.route('/api/resp-events', methods=['GET'])
def resp_events():
    since = request.args.get('since', type=int, default=0)
    new_events = [e for e in recent_resp_events if e['ts'] > since]
    return jsonify(new_events)


@app.route('/api/recent-folios', methods=['GET'])
def recent_folios():
    try:
        client   = get_gspread_client()
        sheet    = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        all_rows = sheet.get_all_values()
        data_rows = all_rows[1:]  # skip header

        results = []
        for raw_idx, row in enumerate(reversed(data_rows)):
            actual_idx = len(data_rows) - raw_idx + 1  # 1-based row in sheet
            padded = row + [''] * 20
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
            })
            if len(results) >= 18:
                break

        return jsonify(results)
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/update', methods=['POST'])
def update_row():
    try:
        data         = request.json
        row_idx      = data.get('row_index')
        status       = data.get('status', '')
        response_text= data.get('response', '')
        link         = data.get('link', '')
        user         = data.get('user', '').lower()

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
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
