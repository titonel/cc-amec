import sqlite3
import json
import os
import requests 
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
DB_PRODUCAO = 'producao_cirurgica.db'
DB_MEDICOS = 'medicos.db'
GEMINI_API_KEY = "AIzaSyA9waj93Js4b8n9aoUtHQcbvWExalaiFG4" 

COLUNAS_MESES = {
    1: 'jan', 2: 'fev', 3: 'mar', 4: 'abr', 5: 'mai', 6: 'jun',
    7: 'jul', 8: 'ago', 9: 'set', 10: 'out', 11: 'nov', 12: 'dez'
}

# --- CONEXÕES ---
def get_producao_conn():
    conn = sqlite3.connect(DB_PRODUCAO)
    conn.row_factory = sqlite3.Row 
    return conn

def get_medicos_conn():
    conn = sqlite3.connect(DB_MEDICOS)
    conn.row_factory = sqlite3.Row
    return conn

# --- AUXILIARES ---
def get_auxiliary_maps():
    conn = get_producao_conn()
    cursor = conn.cursor()
    mapa_esp, mapa_tipo = {}, {}
    try:
        cursor.execute("SELECT * FROM especialidades")
        for r in cursor.fetchall():
            vals = list(r)
            if len(vals) >= 2: mapa_esp[str(vals[0])] = str(vals[1])
        cursor.execute("SELECT * FROM tipo_cma")
        for r in cursor.fetchall():
            vals = list(r)
            if len(vals) >= 2: mapa_tipo[str(vals[0])] = str(vals[1])
    except: pass
    conn.close()
    return mapa_esp, mapa_tipo

# --- ROTAS ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/consulta')
def consulta(): return render_template('consulta.html')

@app.route('/medicos')
def medicos(): return render_template('medicos.html')

# --- API PRODUÇÃO ---
@app.route('/api/search_procedimento')
def search_procedimento():
    term = request.args.get('term', '')
    if len(term) < 3: return jsonify([])
    conn = get_producao_conn()
    cursor = conn.cursor()
    mapa_esp, mapa_tipo = get_auxiliary_maps()
    try:
        cursor.execute("SELECT nome, codigo_sigtap, valor_sigtap FROM procedimentos WHERE nome LIKE ? LIMIT 15", ('%' + term + '%',))
    except sqlite3.OperationalError:
        cursor.execute("SELECT nome, codigo_sus as codigo_sigtap, valor_sigtap FROM procedimentos WHERE nome LIKE ? LIMIT 15", ('%' + term + '%',))
    resultado = []
    for row in cursor.fetchall():
        proc = dict(row)
        cursor.execute("SELECT tipo, especialidade FROM producao WHERE codigo_sigtap = ? LIMIT 1", (proc['codigo_sigtap'],))
        info = cursor.fetchone()
        t, e = "Não classificado", "Geral"
        if info:
            ct, ce = str(info['tipo'] or ''), str(info['especialidade'] or '')
            t = mapa_tipo.get(ct, ct) if ct else t
            e = mapa_esp.get(ce, ce) if ce else e
        proc.update({'tipo_cirurgia': t, 'nome_especialidade': e})
        resultado.append(proc)
    conn.close()
    return jsonify(resultado)

@app.route('/api/submit_producao', methods=['POST'])
def submit_producao():
    data = request.get_json()
    conn = get_producao_conn()
    cursor = conn.cursor()
    try:
        cod = data.get('codigo_sigtap') or data.get('codigo_sus')
        mes, qtd = int(data['mes']), float(data['quantidade'])
        col = COLUNAS_MESES.get(mes)
        if not col: return jsonify({'success': False, 'message': 'Mês inválido'}), 400
        cursor.execute("SELECT id FROM producao WHERE codigo_sigtap = ?", (cod,))
        row = cursor.fetchone()
        col_sql = f'"{col}"' if col in ['set', 'out'] else col
        if row:
            cursor.execute(f"UPDATE producao SET {col_sql} = ? WHERE id = ?", (qtd, row['id']))
            msg = "Atualizado!"
        else:
            cursor.execute(f"INSERT INTO producao (codigo_sigtap, {col_sql}) VALUES (?, ?)", (cod, qtd))
            msg = "Criado!"
        conn.commit()
        return jsonify({'success': True, 'message': msg})
    except Exception as e: return jsonify({'success': False, 'message': str(e)}), 500
    finally: conn.close()

@app.route('/api/producao_mensal', methods=['GET'])
def get_producao_mensal():
    cod, mes = request.args.get('codigo_sigtap'), int(request.args.get('mes', 0))
    col = COLUNAS_MESES.get(mes)
    if not cod or not col: return jsonify({'error': 'Inválido'}), 400
    conn = get_producao_conn()
    col_sql = f'"{col}"' if col in ['set', 'out'] else col
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT t.{col_sql} as q, p.nome, p.valor_sigtap FROM producao t JOIN procedimentos p ON t.codigo_sigtap = p.codigo_sigtap WHERE t.codigo_sigtap = ?", (cod,))
        row = cur.fetchone()
        if row:
            q, v = row['q'] or 0, row['valor_sigtap'] or 0
            return jsonify({'encontrado': True, 'total': q, 'valor_total_produzido': q*v})
        return jsonify({'encontrado': False})
    except: return jsonify({'encontrado': False})
    finally: conn.close()

@app.route('/api/historico', methods=['GET'])
def get_historico():
    cod = request.args.get('codigo_sigtap')
    if not cod: return jsonify({'data': []}), 400
    conn = get_producao_conn()
    cols = ", ".join([f't."{v}"' if v in ['set','out'] else f't.{v}' for v in COLUNAS_MESES.values()])
    cur = conn.cursor()
    cur.execute(f"SELECT {cols} FROM producao t WHERE t.codigo_sigtap = ?", (cod,))
    row = cur.fetchone()
    hist = []
    if row:
        for m in range(1, 13): hist.append({'mes': m, 'total_producao': row[m-1] or 0})
    conn.close()
    return jsonify({'data': hist})

@app.route('/api/analise_ia', methods=['POST'])
def analise_ia():
    if not GEMINI_API_KEY: return jsonify({'error': 'Sem chave'}), 500
    data = request.get_json()
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={"contents": [{"parts": [{"text": f"Analise: {data}"}]}]})
        return jsonify({'markdown': res.json()['candidates'][0]['content']['parts'][0]['text']})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- API: MÉDICOS ---

@app.route('/api/medicos', methods=['GET'])
def get_medicos():
    conn = get_medicos_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM medicos ORDER BY nome")
        medicos = [dict(row) for row in cursor.fetchall()]
        return jsonify(medicos)
    except Exception as e: return jsonify({'error': str(e)}), 500
    finally: conn.close()

@app.route('/api/medicos', methods=['POST'])
def add_medico():
    data = request.get_json()
    conn = get_medicos_conn()
    try:
        # ADICIONADO: 'sexo'
        cols = ['nome', 'crm', 'dn', 'especialidade', 'nacionalidade', 'naturalidade', 'tel_ddd', 'tel_cel', 'email', 'cpf', 'rg', 'cep_res', 'end_res', 'num_res', 'comp_res', 'bairro_res', 'cidade_res', 'estado_res', 'ativo', 'inicio_ativ', 'fim_ativ', 'sexo']
        vals = [data.get(c, '') for c in cols]
        placeholders = ', '.join(['?'] * len(cols))
        cursor = conn.cursor()
        cursor.execute(f"INSERT INTO medicos ({', '.join(cols)}) VALUES ({placeholders})", vals)
        conn.commit()
        return jsonify({'success': True, 'message': 'Médico cadastrado!'})
    except Exception as e: return jsonify({'success': False, 'message': str(e)}), 500
    finally: conn.close()

@app.route('/api/medicos/<int:id>', methods=['PUT'])
def update_medico(id):
    data = request.get_json()
    conn = get_medicos_conn()
    try:
        # ADICIONADO: 'sexo'
        cols = ['nome', 'crm', 'dn', 'especialidade', 'nacionalidade', 'naturalidade', 'tel_ddd', 'tel_cel', 'email', 'cpf', 'rg', 'cep_res', 'end_res', 'num_res', 'comp_res', 'bairro_res', 'cidade_res', 'estado_res', 'ativo', 'inicio_ativ', 'fim_ativ', 'sexo']
        updates = ', '.join([f"{c} = ?" for c in cols])
        vals = [data.get(c, '') for c in cols]
        vals.append(id)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE medicos SET {updates} WHERE id = ?", vals)
        conn.commit()
        return jsonify({'success': True, 'message': 'Atualizado!'})
    except Exception as e: return jsonify({'success': False, 'message': str(e)}), 500
    finally: conn.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)