import sqlite3
import json
import os
import requests
import pandas as pd
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template, redirect, url_for

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False 
app.config['UPLOAD_FOLDER'] = 'uploads'

# Garante que a pasta de uploads existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DB_PRODUCAO = 'producao_cirurgica.db'
DB_MEDICOS = 'medicos.db'
DB_AMB = 'amb.db'
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 

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

def get_amb_conn():
    conn = sqlite3.connect(DB_AMB)
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

# --- ROTAS PRINCIPAIS ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/producao')
def producao_index():
    return render_template('producao_index.html')

@app.route('/producao/cirurgica')
def producao_cirurgica():
    return render_template('producao.html')

@app.route('/medicos')
def medicos_index():
    return render_template('medicos_index.html')

@app.route('/medicos/cadastro')
def medicos_cadastro():
    return render_template('medicos.html')

@app.route('/consulta')
def consulta():
    return render_template('consulta.html')

# --- ROTAS AMBULATORIAL ---

@app.route('/ambulatorial')
def ambulatorial_index():
    return render_template('ambulatorial_index.html')

@app.route('/ambulatorial/robo')
def ambulatorial_robo():
    return render_template('amb_robo.html')

@app.route('/ambulatorial/manual')
def ambulatorial_manual_page():
    """Página de Upload (GET)"""
    return render_template('amb_manual.html')

@app.route('/ambulatorial/manual/analisar', methods=['POST'])
def ambulatorial_analisar():
    """Etapa 1: Recebe arquivo, lê A3/F3 e retorna metadados para confirmação"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Nenhum arquivo enviado'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Arquivo não selecionado'})

    try:
        filename = secure_filename(file.filename)
        # Adiciona timestamp para evitar colisão de nomes
        unique_filename = f"{int(datetime.now().timestamp())}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        ext = filename.rsplit('.', 1)[1].lower()
        
        # 1. Ler Metadados (A3 e F3) - Primeiras 5 linhas
        df_meta = None
        try:
            if ext == 'csv':
                try: df_meta = pd.read_csv(filepath, header=None, nrows=5, sep=';', encoding='latin1')
                except: df_meta = pd.read_csv(filepath, header=None, nrows=5, sep=',', encoding='latin1')
            else:
                try: df_meta = pd.read_excel(filepath, header=None, nrows=5)
                except: 
                    dfs = pd.read_html(filepath, decimal=',', thousands='.', header=None)
                    df_meta = dfs[0].iloc[:5]
        except Exception as e:
            os.remove(filepath)
            return jsonify({'success': False, 'message': f'Erro ao ler metadados: {str(e)}'})

        # Ler Célula A3 (Linha índice 2, Coluna índice 0)
        try:
            val_a3 = str(df_meta.iloc[2, 0]).strip()
        except:
            val_a3 = "Desconhecido"

        # Ler Célula F3 (Linha índice 2, Coluna índice 5)
        try:
            if df_meta.shape[1] > 5:
                val_f3 = str(df_meta.iloc[2, 5]).strip()
            else:
                # Fallback: procura padrão de data na linha
                val_f3 = "Data não encontrada"
                for c in range(df_meta.shape[1]):
                    v = str(df_meta.iloc[2, c])
                    if " de " in v and any(char.isdigit() for char in v):
                        val_f3 = v; break
        except:
            val_f3 = "Erro na leitura"

        # Determinar Tipo (Consulta vs Exame)
        tipo_identificado = "Desconhecido"
        target_table = ""
        
        if 'consulta' in val_a3.lower():
            tipo_identificado = "Consulta"
            target_table = "producao_amb"
        elif 'exame' in val_a3.lower():
            tipo_identificado = "Exame"
            target_table = "producao_exame"
        
        if target_table == "":
             os.remove(filepath)
             return jsonify({'success': False, 'message': f'Tipo de arquivo não reconhecido na célula A3 ("{val_a3}"). Esperado "Consulta" ou "Exame".'})

        # Retorna dados para o frontend confirmar
        return jsonify({
            'success': True,
            'confirmation_required': True,
            'filename': unique_filename, # Nome temporário para o próximo passo
            'tipo_arquivo': val_a3,      # Texto original A3
            'tipo_sistema': tipo_identificado, # Lógica interna
            'mes_ano': val_f3            # Texto original F3
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro crítico na análise: {str(e)}'})

@app.route('/ambulatorial/manual/confirmar', methods=['POST'])
def ambulatorial_confirmar():
    """Etapa 2: Processa o arquivo após confirmação do usuário"""
    data = request.get_json()
    filename = data.get('filename')
    
    if not filename:
        return jsonify({'success': False, 'message': 'Nome de arquivo inválido.'})
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'Arquivo expirou ou não existe. Faça o upload novamente.'})

    try:
        ext = filename.rsplit('.', 1)[1].lower()

        # Relê metadados para garantir integridade (A3/F3)
        # Repetimos a lógica para decidir a tabela, garantindo segurança no backend
        df_meta = None
        # (Lógica de leitura igual à etapa 1 para pegar A3)
        if ext == 'csv':
            try: df_meta = pd.read_csv(filepath, header=None, nrows=5, sep=';', encoding='latin1')
            except: df_meta = pd.read_csv(filepath, header=None, nrows=5, sep=',', encoding='latin1')
        else:
            try: df_meta = pd.read_excel(filepath, header=None, nrows=5)
            except: df_meta = pd.read_html(filepath, decimal=',', thousands='.', header=None)[0].iloc[:5]
            
        val_a3 = str(df_meta.iloc[2, 0]).strip()
        val_f3 = str(df_meta.iloc[2, 5] if df_meta.shape[1] > 5 else "").strip()
        # Fallback F3
        if not val_f3 or " de " not in val_f3:
             for c in range(df_meta.shape[1]):
                v = str(df_meta.iloc[2, c])
                if " de " in v: val_f3 = v; break

        # Decisão de Tabela
        tabela_destino = ""
        if 'consulta' in val_a3.lower(): tabela_destino = "producao_amb"
        elif 'exame' in val_a3.lower(): tabela_destino = "producao_exame"
        else: raise Exception("Tipo de arquivo inválido.")

        # Parsing de Data (F3)
        try:
            partes = val_f3.lower().split(' de ')
            mes_arquivo = partes[0].capitalize()
            ano_arquivo = int(partes[1])
        except:
            mes_arquivo = val_f3
            ano_arquivo = 0

        # --- LEITURA DOS DADOS (Mesma lógica robusta anterior) ---
        # 1. Localizar Cabeçalho (Procura "Especialidade" nas primeiras 15 linhas)
        df_preview = None
        if ext == 'csv':
            try: df_preview = pd.read_csv(filepath, header=None, nrows=15, sep=';', encoding='latin1')
            except: df_preview = pd.read_csv(filepath, header=None, nrows=15, sep=',', encoding='latin1')
        else:
            try: df_preview = pd.read_excel(filepath, header=None, nrows=15)
            except: df_preview = pd.read_html(filepath, decimal=',', thousands='.', header=None)[0].iloc[:15]

        header_idx = -1
        for idx, row in df_preview.iterrows():
            row_str = str(row.values).lower()
            if 'especialidade' in row_str and 'oferta' in row_str:
                header_idx = idx
                break
        
        if header_idx == -1: raise Exception("Cabeçalho não encontrado.")

        # 2. Ler Dados
        if ext == 'csv':
            df_dados = pd.read_csv(filepath, header=header_idx, sep=';', encoding='latin1') if ';' in open(filepath, encoding='latin1').read() else pd.read_csv(filepath, header=header_idx, sep=',', encoding='latin1')
        else:
            try: df_dados = pd.read_excel(filepath, header=header_idx)
            except: df_dados = pd.read_html(filepath, decimal=',', thousands='.', header=header_idx)[0]

        # 3. Mapear Colunas (4 primeiras fixas)
        if df_dados.shape[1] < 4: raise Exception("Menos de 4 colunas encontradas.")
        
        df_trabalho = df_dados.iloc[:, :4].copy()
        df_trabalho.columns = ['especialidade', 'oferta', 'agendado', 'realizado']
        df_trabalho = df_trabalho.dropna(how='all')

        # 4. Inserir no Banco
        conn = get_amb_conn()
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        usuario = 'bot'

        registros = 0
        for _, row in df_trabalho.iterrows():
            esp = str(row['especialidade']).strip()
            if not esp or esp.lower() in ['nan', 'total', 'especialidade', 'none']: continue
            
            def safe_int(val):
                try: return int(float(str(val).replace('.', '').replace(',', '.')))
                except: return 0

            oferta = safe_int(row['oferta'])
            agendado = safe_int(row['agendado'])
            realizado = safe_int(row['realizado'])

            cursor.execute(f"""
                INSERT INTO {tabela_destino} (especialidade, oferta, agendado, realizado, mes, ano, usuario, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (esp, oferta, agendado, realizado, mes_arquivo, ano_arquivo, usuario, timestamp))
            registros += 1

        conn.commit()
        conn.close()
        
        os.remove(filepath) # Limpeza final

        return jsonify({
            'success': True, 
            'message': f'Sucesso! {registros} registros importados para tabela {tabela_destino}.'
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro no processamento: {str(e)}'})

# --- DEMAIS ROTAS (MANTIDAS) ---
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
    if not GEMINI_API_KEY: return jsonify({'error': 'Sem chave API configurada'}), 500
    data = request.get_json()
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={"contents": [{"parts": [{"text": f"Analise: {data}"}]}]})
        return jsonify({'markdown': res.json()['candidates'][0]['content']['parts'][0]['text']})
    except Exception as e: return jsonify({'error': str(e)}), 500

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

@app.route('/api/especialidades_amec', methods=['GET'])
def get_especialidades_amec():
    conn = get_medicos_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT especialidade FROM especialidades_amec ORDER BY especialidade ASC")
        lista = [row['especialidade'] for row in cursor.fetchall()]
        return jsonify(lista)
    except Exception as e: return jsonify([]), 500
    finally: conn.close()

@app.route('/api/medicos', methods=['POST'])
def add_medico():
    data = request.get_json()
    conn = get_medicos_conn()
    try:
        cols = ['nome', 'crm', 'dn', 'especialidade', 'nacionalidade', 'naturalidade', 'estado_natural', 'tel_ddd', 'tel_cel', 'email', 'cpf', 'rg', 'cep_res', 'end_res', 'num_res', 'comp_res', 'bairro_res', 'cidade_res', 'estado_res', 'ativo', 'inicio_ativ', 'fim_ativ', 'sexo']
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
        cols = ['nome', 'crm', 'dn', 'especialidade', 'nacionalidade', 'naturalidade', 'estado_natural', 'tel_ddd', 'tel_cel', 'email', 'cpf', 'rg', 'cep_res', 'end_res', 'num_res', 'comp_res', 'bairro_res', 'cidade_res', 'estado_res', 'ativo', 'inicio_ativ', 'fim_ativ', 'sexo']
        updates = ', '.join([f"{c} = ?" for c in cols])
        vals = [data.get(c, '') for c in cols]
        vals.append(id)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE medicos SET {updates} WHERE id = ?", vals)
        conn.commit()
        return jsonify({'success': True, 'message': 'Atualizado!'})
    except Exception as e: return jsonify({'success': False, 'message': str(e)}), 500
    finally: conn.close()

@app.route('/api/siresp/sync', methods=['POST'])
def siresp_sync():
    def generate():
        yield json.dumps({"status": "info", "message": "Iniciando robô..."}) + "\n"
        yield json.dumps({"status": "success", "message": "Finalizado."}) + "\n"
    return app.response_class(generate(), mimetype='application/json')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)