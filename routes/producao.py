from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from database import get_producao_conn
import os
import requests

producao_bp = Blueprint('producao', __name__)

COLUNAS_MESES = {
    1: 'jan', 2: 'fev', 3: 'mar', 4: 'abr', 5: 'mai', 6: 'jun',
    7: 'jul', 8: 'ago', 9: 'set', 10: 'out', 11: 'nov', 12: 'dez'
}

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_auxiliary_maps():
    conn = get_producao_conn()
    cursor = conn.cursor()
    mapa_esp, mapa_tipo = {}, {}
    try:
        cursor.execute("SELECT * FROM especialidades")
        for r in cursor.fetchall():
            if len(list(r)) >= 2: mapa_esp[str(r[0])] = str(r[1])
        cursor.execute("SELECT * FROM tipo_cma")
        for r in cursor.fetchall():
            if len(list(r)) >= 2: mapa_tipo[str(r[0])] = str(r[1])
    except: pass
    conn.close()
    return mapa_esp, mapa_tipo

@producao_bp.route('/producao')
@login_required
def index():
    return render_template('producao_index.html')

@producao_bp.route('/producao/cirurgica')
@login_required
def cirurgica():
    return render_template('producao.html')

@producao_bp.route('/api/search_procedimento')
@login_required
def search_procedimento():
    term = request.args.get('term', '')
    if len(term) < 3: return jsonify([])
    conn = get_producao_conn()
    cursor = conn.cursor()
    mapa_esp, mapa_tipo = get_auxiliary_maps()
    try:
        cursor.execute("SELECT nome, codigo_sigtap, valor_sigtap FROM procedimentos WHERE nome LIKE ? LIMIT 15", ('%' + term + '%',))
    except:
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

@producao_bp.route('/api/submit_producao', methods=['POST'])
@login_required
def submit_producao():
    data = request.get_json()
    conn = get_producao_conn()
    cursor = conn.cursor()
    try:
        cod = data.get('codigo_sigtap') or data.get('codigo_sus')
        mes, qtd = int(data['mes']), float(data['quantidade'])
        col = COLUNAS_MESES.get(mes)
        cursor.execute("SELECT id FROM producao WHERE codigo_sigtap = ?", (cod,))
        row = cursor.fetchone()
        col_sql = f'"{col}"' if col in ['set', 'out'] else col
        if row: cursor.execute(f"UPDATE producao SET {col_sql} = ? WHERE id = ?", (qtd, row['id']))
        else: cursor.execute(f"INSERT INTO producao (codigo_sigtap, {col_sql}) VALUES (?, ?)", (cod, qtd))
        conn.commit()
        return jsonify({'success': True, 'message': 'Salvo'})
    except Exception as e: return jsonify({'success': False, 'message': str(e)}), 500
    finally: conn.close()

@producao_bp.route('/api/producao_mensal', methods=['GET'])
@login_required
def get_producao_mensal():
    cod, mes = request.args.get('codigo_sigtap'), int(request.args.get('mes', 0))
    col = COLUNAS_MESES.get(mes)
    conn = get_producao_conn()
    col_sql = f'"{col}"' if col in ['set', 'out'] else col
    try:
        res = conn.execute(f"SELECT t.{col_sql} as q, p.nome, p.valor_sigtap FROM producao t JOIN procedimentos p ON t.codigo_sigtap = p.codigo_sigtap WHERE t.codigo_sigtap = ?", (cod,)).fetchone()
        if res: return jsonify({'encontrado': True, 'total': res['q'] or 0, 'valor_total_produzido': (res['q'] or 0) * (res['valor_sigtap'] or 0)})
        return jsonify({'encontrado': False})
    except: return jsonify({'encontrado': False})
    finally: conn.close()

@producao_bp.route('/api/historico', methods=['GET'])
@login_required
def get_historico():
    cod = request.args.get('codigo_sigtap')
    conn = get_producao_conn()
    cols = ", ".join([f't."{v}"' if v in ['set','out'] else f't.{v}' for v in COLUNAS_MESES.values()])
    res = conn.execute(f"SELECT {cols} FROM producao t WHERE t.codigo_sigtap = ?", (cod,)).fetchone()
    hist = [{'mes': m, 'total_producao': res[m-1] or 0} for m in range(1, 13)] if res else []
    conn.close()
    return jsonify({'data': hist})

@producao_bp.route('/api/analise_ia', methods=['POST'])
@login_required
def analise_ia():
    if not GEMINI_API_KEY: return jsonify({'error': 'Sem chave API'}), 500
    data = request.get_json()
    try:
        res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}", json={"contents": [{"parts": [{"text": f"Analise: {data}"}]}]})
        return jsonify({'markdown': res.json()['candidates'][0]['content']['parts'][0]['text']})
    except Exception as e: return jsonify({'error': str(e)}), 500