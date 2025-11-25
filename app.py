import sqlite3
import json
import os
import requests
import pandas as pd
import re
import pdfplumber # Requer pip install pdfplumber
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False 
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = 'chave_super_secreta_amec_2025' 

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar o sistema."

# --- BANCOS DE DADOS ---
DB_FOLDER = 'db'
DB_PRODUCAO = os.path.join(DB_FOLDER, 'producao_cirurgica.db')
DB_MEDICOS = os.path.join(DB_FOLDER, 'medicos.db')
DB_AMB = os.path.join(DB_FOLDER, 'amb.db')
DB_CADASTRO = os.path.join(DB_FOLDER, 'cadastro.db')

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 

COLUNAS_MESES = {
    1: 'jan', 2: 'fev', 3: 'mar', 4: 'abr', 5: 'mai', 6: 'jun',
    7: 'jul', 8: 'ago', 9: 'set', 10: 'out', 11: 'nov', 12: 'dez'
}

# --- MODELO DE USUÁRIO ---
class User(UserMixin):
    def __init__(self, id, nome, email, nivel_acesso, primeiro_acesso):
        self.id = id
        self.nome = nome
        self.email = email
        self.nivel_acesso = nivel_acesso
        self.primeiro_acesso = primeiro_acesso

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(DB_CADASTRO)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome_completo, email, nivel_acesso, primeiro_acesso FROM usuarios WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return User(id=row[0], nome=row[1], email=row[2], nivel_acesso=row[3], primeiro_acesso=row[4])
    return None

# --- CONEXÕES ---
def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_producao_conn(): return get_db_connection(DB_PRODUCAO)
def get_medicos_conn(): return get_db_connection(DB_MEDICOS)
def get_amb_conn(): return get_db_connection(DB_AMB)
def get_cadastro_conn(): return get_db_connection(DB_CADASTRO)

# --- AUXILIARES ---
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

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        conn = get_cadastro_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        user_data = cursor.fetchone()
        conn.close()
        if user_data and check_password_hash(user_data['senha_hash'], senha):
            user_obj = User(user_data['id'], user_data['nome_completo'], user_data['email'], user_data['nivel_acesso'], user_data['primeiro_acesso'])
            login_user(user_obj)
            if user_data['primeiro_acesso'] == 1: return redirect(url_for('primeiro_acesso'))
            return redirect(url_for('index'))
        else:
            flash('Email ou senha inválidos.', 'error')
    return render_template('login.html')

@app.route('/primeiro_acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if current_user.primeiro_acesso == 0: return redirect(url_for('index'))
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirma_senha = request.form.get('confirma_senha')
        if nova_senha != confirma_senha: flash('As senhas não conferem.', 'error')
        elif len(nova_senha) < 6: flash('A senha deve ter no mínimo 6 caracteres.', 'error')
        else:
            novo_hash = generate_password_hash(nova_senha)
            conn = get_cadastro_conn()
            conn.execute("UPDATE usuarios SET senha_hash = ?, primeiro_acesso = 0 WHERE id = ?", (novo_hash, current_user.id))
            conn.commit()
            conn.close()
            current_user.primeiro_acesso = 0
            flash('Senha alterada com sucesso!', 'success')
            return redirect(url_for('index'))
    return render_template('primeiro_acesso.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- MÓDULO EMPRESAS (NOVO) ---

def extrair_dados_pdf(filepath):
    """Extrai dados do contrato usando pdfplumber e regex"""
    dados = {
        'razao_social': '',
        'cnpj': '',
        'objeto': '',
        'data': '',
        'escopo': []
    }
    
    with pdfplumber.open(filepath) as pdf:
        full_text = ""
        # Extração de Texto Corrido
        for page in pdf.pages:
            text = page.extract_text()
            if text: full_text += text + "\n"
            
            # Extração de Tabelas (Escopo)
            tables = page.extract_tables()
            for table in tables:
                # Limpeza simples de tabelas vazias ou cabeçalhos repetidos
                for row in table:
                    # Filtra linhas que parecem conter dados de produção (Consultas, Exames, Cirurgias)
                    if row and any(k in str(row).lower() for k in ['consulta', 'exame', 'cirurgia', 'plantão', 'valor', 'média']):
                        # Remove Nones e quebras de linha
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else '' for cell in row]
                        dados['escopo'].append(clean_row)

        # 1. Razão Social (Busca padrão "Pelo presente, [NOME], inscrito")
        match_razao = re.search(r'Pelo presente,\s*(.*?),\s*inscrito no CNPJ', full_text, re.IGNORECASE)
        if match_razao:
            dados['razao_social'] = match_razao.group(1).upper()
        else:
            # Tenta pegar logo no início se falhar
            match_razao_alt = re.search(r'CONTRATADA:\s*(.*?)\s', full_text)
            if match_razao_alt: dados['razao_social'] = match_razao_alt.group(1).upper()

        # 2. CNPJ
        match_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', full_text)
        if match_cnpj:
            dados['cnpj'] = match_cnpj.group(0)

        # 3. Objeto (Busca "Constitui objeto..." ou "1.1")
        match_obj = re.search(r'Constitui objeto do presente contrato\s*(.*?)\.', full_text, re.IGNORECASE | re.DOTALL)
        if match_obj:
            dados['objeto'] = match_obj.group(1).replace('\n', ' ').strip()

        # 4. Data de Celebração (Geralmente no final: "São Paulo, dd de mm de aaaa")
        # Pega a última ocorrência de data no texto
        match_dates = re.findall(r'([A-Za-zçã]+),\s*(\d{1,2})\s*de\s*([A-Za-zç]+)\s*de\s*(\d{4})', full_text)
        if match_dates:
            # Formata a última data encontrada
            local, dia, mes, ano = match_dates[-1]
            dados['data'] = f"{dia} de {mes} de {ano}"

    return dados

@app.route('/empresas/cadastro', methods=['GET'])
@login_required
def empresas_cadastro_page():
    return render_template('empresas_cadastro.html')

@app.route('/empresas/upload', methods=['POST'])
@login_required
def empresas_upload():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Nenhum arquivo enviado'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Arquivo inválido'})

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Extração Inteligente
        dados_extraidos = extrair_dados_pdf(filepath)
        
        return jsonify({
            'success': True,
            'data': dados_extraidos,
            'filename': filename
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro na leitura do contrato: {str(e)}'})

@app.route('/empresas/salvar', methods=['POST'])
@login_required
def empresas_salvar():
    try:
        data = request.get_json()
        conn = get_cadastro_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO empresas (razao_social, cnpj, objeto_contrato, data_celebracao, escopo_json, arquivo_contrato)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data.get('razao_social'),
            data.get('cnpj'),
            data.get('objeto'),
            data.get('data'),
            json.dumps(data.get('escopo')), # Salva tabela como JSON
            data.get('filename')
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Empresa cadastrada com sucesso!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao salvar: {str(e)}'})

# --- ROTAS DE USUÁRIOS (CONFIGURAÇÕES) ---
@app.route('/configuracoes/usuarios', methods=['GET', 'POST'])
@login_required
def cadastro_usuario():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome')
            sexo = request.form.get('sexo')
            drt = request.form.get('drt')
            celular = request.form.get('celular')
            ramal = request.form.get('ramal')
            email = request.form.get('email')
            nivel = request.form.get('nivel')
            senha_inicial = generate_password_hash(drt)
            
            conn = get_cadastro_conn()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usuarios (nome_completo, sexo, drt, celular, ramal, email, nivel_acesso, senha_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (nome, sexo, drt, celular, ramal, email, nivel, senha_inicial))
            conn.commit()
            conn.close()
            flash('Usuário cadastrado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash('Erro: Este e-mail já está cadastrado.', 'error')
        except Exception as e:
            flash(f'Erro ao cadastrar: {str(e)}', 'error')
    return render_template('cadastro_usuario.html')

# --- ROTAS PRINCIPAIS ---
@app.route('/')
@login_required
def index():
    if current_user.primeiro_acesso == 1: return redirect(url_for('primeiro_acesso'))
    return render_template('index.html')

@app.route('/producao')
@login_required
def producao_index(): return render_template('producao_index.html')

@app.route('/producao/cirurgica')
@login_required
def producao_cirurgica(): return render_template('producao.html')

@app.route('/medicos')
@login_required
def medicos_index(): return render_template('medicos_index.html')

@app.route('/medicos/cadastro')
@login_required
def medicos_cadastro(): return render_template('medicos.html')

@app.route('/consulta')
@login_required
def consulta(): return render_template('consulta.html')

@app.route('/ambulatorial')
@login_required
def ambulatorial_index(): return render_template('ambulatorial_index.html')

@app.route('/ambulatorial/robo')
@login_required
def ambulatorial_robo(): return render_template('amb_robo.html')

@app.route('/ambulatorial/visualizar')
@login_required
def ambulatorial_visualizar(): return render_template('amb_visualizacao_index.html')

@app.route('/ambulatorial/visualizar/dashboard')
@login_required
def ambulatorial_dashboard(): return "<h1>Dashboard em construção...</h1><a href='/ambulatorial/visualizar'>Voltar</a>"

@app.route('/ambulatorial/visualizar/tabelas')
@login_required
def ambulatorial_tabelas(): return render_template('amb_tabelas.html')

@app.route('/ambulatorial/manual')
@login_required
def ambulatorial_manual_page(): return render_template('amb_manual.html')

# --- ROTAS DE APIs AUXILIARES (Mantidas simplificadas para brevidade, mesmo conteúdo anterior) ---
@app.route('/ambulatorial/manual/analisar', methods=['POST'])
@login_required
def ambulatorial_analisar():
    # ... (CÓDIGO EXISTENTE MANTIDO) ...
    # (Para poupar espaço, assuma que o código da resposta anterior está aqui. 
    # Se precisar que eu repita, avise, mas a lógica de leitura de XLS/CSV está inalterada)
    pass 

# (Nota: Para funcionar, você deve manter as funções ambulatorial_analisar e ambulatorial_confirmar 
# que escrevemos na resposta anterior aqui dentro)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)