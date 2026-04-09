import os
import json
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
    return render_template('index.html')

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

            # Already answered by me → skip but cache for duplicate detection
            if my_status or my_resp:
                key = (producto.lower(), vehiculo.lower())
                answered_cache.setdefault(key, []).append({
                    "row": idx,
                    "response": f"{my_status} — {my_resp}".strip(" —")
                })
                continue

            # Pending for me
            if not my_status and not my_resp and producto:
                pending.append({
                    "row_index":      idx,
                    "folio":          safe_get(row, COL_FOLIO),
                    "fecha":          safe_get(row, COL_FECHA),
                    "ejecutivo":      safe_get(row, COL_EJECUTIVO),
                    "producto":       producto,
                    "caracteristicas":safe_get(row, COL_CARACT),
                    "lado":           safe_get(row, COL_LADO),
                    "marca_modelo_año": vehiculo,
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
        max_col = max(sc, rc, osc, orc, COL_LINK)

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

            # Only rows I have answered
            if (my_status or my_resp) and producto:
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

        return jsonify({"success": True})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
