import sqlite3
import json
import os
import requests 
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
DB_NAME = 'producao_cirurgica.db'
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyA9waj93Js4b8n9aoUtHQcbvWExalaiFG4") 

def get_db_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/consulta')
def consulta():
    return render_template('consulta.html')

@app.route('/api/search_procedimento')
def search_procedimento():
    term = request.args.get('term', '')
    if len(term) < 3:
        return jsonify([])

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT nome, codigo_sus, valor_sigtap FROM procedimentos WHERE nome LIKE ? LIMIT 10",
        ('%' + term + '%',)
    )
    procedimentos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(procedimentos)

@app.route('/api/submit_producao', methods=['POST'])
def submit_producao():
    data = request.get_json()
    try:
        codigo_sus = data['codigo_sus']
        ano = int(data['ano'])
        mes = int(data['mes'])
        quantidade = int(data['quantidade'])
        if not (1 <= mes <= 12) or not (2020 <= ano <= 2030) or not (quantidade > 0):
             raise ValueError("Valores inválidos")
    except (KeyError, ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM procedimentos WHERE codigo_sus = ?", (codigo_sus,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Código SUS não encontrado.'}), 404
    
    try:
        cursor.execute(
            "INSERT INTO producao (procedimento_id, ano, mes, quantidade) VALUES (?, ?, ?, ?)",
            (row['id'], ano, mes, quantidade)
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Erro: {e}'}), 500
    
    conn.close()
    return jsonify({'success': True, 'message': 'Registrado!'})

# --- NOVOS ENDPOINTS DE CONSULTA ---

@app.route('/api/producao_mensal', methods=['GET'])
def get_producao_mensal():
    """Consulta a produção de um procedimento em um mês/ano específico."""
    codigo_sus = request.args.get('codigo_sus')
    mes = request.args.get('mes')
    ano = request.args.get('ano')

    if not all([codigo_sus, mes, ano]):
        return jsonify({'error': 'Parâmetros insuficientes'}), 400

    conn = get_db_conn()
    cursor = conn.cursor()
    
    query = """
    SELECT SUM(t.quantidade) as total, p.nome, p.valor_sigtap
    FROM producao t
    JOIN procedimentos p ON t.procedimento_id = p.id
    WHERE p.codigo_sus = ? AND t.mes = ? AND t.ano = ?
    """
    cursor.execute(query, (codigo_sus, mes, ano))
    row = cursor.fetchone()
    conn.close()

    if row and row['total'] is not None:
        return jsonify({
            'encontrado': True,
            'procedimento': row['nome'],
            'total': row['total'],
            'valor_unitario': row['valor_sigtap'],
            'valor_total_produzido': row['total'] * (row['valor_sigtap'] or 0)
        })
    else:
        return jsonify({'encontrado': False})

@app.route('/api/historico', methods=['GET'])
def get_historico():
    """Série histórica para o gráfico."""
    codigo_sus = request.args.get('codigo_sus')
    ano_inicio = request.args.get('ano_inicio')
    ano_fim = request.args.get('ano_fim')
    
    if not codigo_sus:
        return jsonify({'data': []}), 400
    
    conn = get_db_conn()
    cursor = conn.cursor()
    
    query = """
    SELECT p.nome, t.ano, t.mes, SUM(t.quantidade) as total_producao
    FROM producao t
    JOIN procedimentos p ON t.procedimento_id = p.id
    WHERE p.codigo_sus = ?
    """
    params = [codigo_sus]
    
    if ano_inicio and ano_fim:
        query += " AND t.ano BETWEEN ? AND ?"
        params.extend([ano_inicio, ano_fim])
    
    query += " GROUP BY t.ano, t.mes, p.nome ORDER BY t.ano, t.mes"
    
    cursor.execute(query, params)
    historico = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'data': historico})

@app.route('/api/analise_ia', methods=['POST'])
def analise_ia():
    """Endpoint para análise Gemini (mantido)."""
    if not GEMINI_API_KEY:
        return jsonify({'error': 'Sem chave API configurada.'}), 500
    
    data = request.get_json()
    historico = data.get('historico', [])
    proc_name = data.get('proc_name', 'Procedimento')

    if not historico:
        return jsonify({'error': 'Sem dados.'}), 400

    dados_txt = "\n".join([f"- {h['mes']}/{h['ano']}: {h['total_producao']}" for h in historico])
    prompt = f"Analise a produção de {proc_name}:\n{dados_txt}\nIdentifique tendências, picos e sugira ações. Responda em Markdown."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}"
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
        resp.raise_for_status()
        return jsonify({'markdown': resp.json()['candidates'][0]['content']['parts'][0]['text']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)