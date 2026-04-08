import os
import json
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Google Sheets Configuration
SHEET_ID = '1J3t28M_0oZuVjkZ8GxNrD08kiGqd-A08I23jAiv8dPU'
SHEET_NAME = 'Base'

# Mapping Columns (1-indexed for gspread, 0-indexed for list access)
COL_FOLIO = 2      # B
COL_PRODUCTO = 5   # E
COL_CARACT = 6     # F
COL_LADO = 7       # G
COL_VEHICULO = 8   # H
COL_LA_REINA_STATUS = 10  # J
COL_LA_REINA_RESP = 11    # K

def get_gspread_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    # If credentials.json exists, use it. Otherwise, look for env var.
    if os.path.exists('credentials.json'):
        creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    elif os.environ.get('GOOGLE_CREDENTIALS_JSON'):
        creds_dict = json.loads(os.environ.get('GOOGLE_CREDENTIALS_JSON'))
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        raise Exception("No Google credentials found. Please provide credentials.json or GOOGLE_CREDENTIALS_JSON env var.")
    
    return gspread.authorize(creds)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/pending', methods=['GET'])
def get_pending():
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        all_rows = sheet.get_all_values()
        
        # Header is row 1
        headers = all_rows[0]
        data_rows = all_rows[1:]
        
        pending = []
        # Store previous answers for duplicate detection
        answered_cache = {}
        for idx, row in enumerate(data_rows, start=2):
            if len(row) < COL_LA_REINA_RESP: # Padding if row is short
                row.extend([''] * (COL_LA_REINA_RESP - len(row)))
                
            status = row[COL_LA_REINA_STATUS-1].strip()
            producto = row[COL_PRODUCTO-1].strip()
            vehiculo = row[COL_VEHICULO-1].strip()
            respuesta = row[COL_LA_REINA_RESP-1].strip()
            
            # If it's answered, cache it for duplicate check
            if status or respuesta:
                key = (producto.lower(), vehiculo.lower())
                if key not in answered_cache:
                    answered_cache[key] = []
                answered_cache[key].append({"row": idx, "response": f"[{status}] {respuesta}"})
                continue
            
            # If it's pending (no status and no response)
            if not status and not respuesta and producto:
                pending.append({
                    "row_index": idx,
                    "folio": row[COL_FOLIO-1],
                    "producto": producto,
                    "caracteristicas": row[COL_CARACT-1],
                    "lado": row[COL_LADO-1],
                    "marca_modelo_año": vehiculo,
                    "ejecutivo": row[3], # Column D
                    "duplicates": []
                })
        
        # Add duplicate info
        for p in pending:
            key = (p["producto"].lower(), p["marca_modelo_año"].lower())
            if key in answered_cache:
                p["duplicates"] = answered_cache[key]
                
        return jsonify(pending)
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/update', methods=['POST'])
def update_row():
    try:
        data = request.json
        row_idx = data.get('row_index')
        status = data.get('status')
        response_text = data.get('response')
        
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        
        # Update Status (J) and Response (K)
        # update_cells or discrete updates
        sheet.update_cell(row_idx, COL_LA_REINA_STATUS, status)
        sheet.update_cell(row_idx, COL_LA_REINA_RESP, response_text)
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
