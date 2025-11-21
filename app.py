import sqlite3
import json
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
DB_NAME = 'producao_cirurgica.db'

def get_db_conn():
    """Conecta ao banco de dados SQLite."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Serve a página HTML principal."""
    # O HTML é retornado como uma string (template string)
    # para manter tudo em um único arquivo.
    return render_template('index.html')

@app.route('/api/search_procedimento')
def search_procedimento():
    """Endpoint da API para buscar procedimentos pelo nome."""
    term = request.args.get('term', '')
    if len(term) < 3:
        # Não busca por termos muito curtos
        return jsonify([])

    conn = get_db_conn()
    cursor = conn.cursor()
    # Busca procedimentos que contenham o termo, limitando a 10 resultados
    cursor.execute(
        "SELECT nome, codigo_sus, valor_sigtap FROM procedimentos WHERE nome LIKE ? LIMIT 10",
        ('%' + term + '%',)
    )
    # Converte os resultados em uma lista de dicionários
    procedimentos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Retorna os resultados como JSON
    return jsonify(procedimentos)

@app.route('/api/submit_producao', methods=['POST'])
def submit_producao():
    """Endpoint da API para salvar um novo registro de produção."""
    data = request.get_json()

    try:
        # Validação simples dos dados recebidos
        codigo_sus = data['codigo_sus']
        ano = int(data['ano'])
        mes = int(data['mes'])
        quantidade = int(data['quantidade'])
        
        if not (1 <= mes <= 12) or not (2020 <= ano <= 2030) or not (quantidade > 0):
             raise ValueError("Valores inválidos")

    except (KeyError, ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Dados inválidos ou ausentes.'}), 400

    conn = get_db_conn()
    cursor = conn.cursor()
    
    # 1. Encontrar o ID do procedimento com base no código SUS
    cursor.execute("SELECT id FROM procedimentos WHERE codigo_sus = ?", (codigo_sus,))
    procedimento_row = cursor.fetchone()
    
    if not procedimento_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Erro: Código SUS não encontrado no banco de dados.'}), 404
        
    procedimento_id = procedimento_row['id']
    
    # 2. Inserir o novo registro de produção
    try:
        cursor.execute(
            "INSERT INTO producao (procedimento_id, ano, mes, quantidade) VALUES (?, ?, ?, ?)",
            (procedimento_id, ano, mes, quantidade)
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Erro ao salvar no banco de dados: {e}'}), 500
    
    conn.close()
    
    # Retorna sucesso
    return jsonify({'success': True, 'message': 'Produção registrada com sucesso!'})

@app.route('/index.html')
def index_html():
    """Redirecionamento caso o usuário digite /index.html"""
    return index()

# --- Bloco principal para rodar o servidor ---
if __name__ == '__main__':
    print("Iniciando servidor Flask em http://127.0.0.1:5000")
    print("Execute o script 'setup_database.py' primeiro se ainda não o fez.")
    app.run(debug=True, host='0.0.0.0', port=5000)