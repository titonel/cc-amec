import sqlite3
import json
import os
import requests
import pandas as pd
import re
import pdfplumber
import uuid
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = 'chave_super_secreta_amec_2025'

# Garante que a pasta de uploads existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Configuração Flask-Login
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


# --- HELPER FUNCTIONS DE DATA ---
def parse_data_banco(data_str):
    """Tenta converter string de data (DD/MM/YYYY ou YYYY-MM-DD) para objeto date"""
    if not data_str: return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(data_str, fmt).date()
        except ValueError:
            pass
    return None


def add_months(source_date, months):
    """Adiciona meses a uma data corretamente"""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, [31,
                                29 if year % 4 == 0 and not year % 100 == 0 or year % 400 == 0 else 28,
                                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


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
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return User(id=row['id'], nome=row['nome_completo'], email=row['email'], nivel_acesso=row['nivel_acesso'],
                    primeiro_acesso=row['primeiro_acesso'])
    return None


# --- CONEXÕES ---
def get_db_connection(db_path):
    if not os.path.exists(db_path):
        print(f"AVISO: Banco de dados não encontrado em {db_path}")
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
    except:
        pass
    conn.close()
    return mapa_esp, mapa_tipo


def calcular_idade(data_nasc_str):
    try:
        if not data_nasc_str: return None
        nasc = datetime.strptime(data_nasc_str, "%Y-%m-%d").date()
        hoje = date.today()
        return hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
    except:
        return None


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
            user_obj = User(
                id=user_data['id'],
                nome=user_data['nome_completo'],
                email=user_data['email'],
                nivel_acesso=user_data['nivel_acesso'],
                primeiro_acesso=user_data['primeiro_acesso']
            )
            login_user(user_obj)

            if user_data['primeiro_acesso'] == 1:
                return redirect(url_for('primeiro_acesso'))

            return redirect(url_for('index'))
        else:
            flash('Email ou senha inválidos.', 'error')

    return render_template('login.html')


@app.route('/primeiro_acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if current_user.primeiro_acesso == 0:
        return redirect(url_for('index'))

    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirma_senha = request.form.get('confirma_senha')

        if nova_senha != confirma_senha:
            flash('As senhas não conferem.', 'error')
        elif len(nova_senha) < 6:
            flash('A senha deve ter no mínimo 6 caracteres.', 'error')
        else:
            novo_hash = generate_password_hash(nova_senha)
            conn = get_cadastro_conn()
            conn.execute("UPDATE usuarios SET senha_hash = ?, primeiro_acesso = 0 WHERE id = ?",
                         (novo_hash, current_user.id))
            conn.commit()
            conn.close()

            # Atualiza sessão
            current_user.primeiro_acesso = 0
            flash('Senha alterada com sucesso!', 'success')
            return redirect(url_for('index'))

    return render_template('primeiro_acesso.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# --- ROTAS PRINCIPAIS DE NAVEGAÇÃO ---

@app.route('/')
@login_required
def index():
    if current_user.primeiro_acesso == 1: return redirect(url_for('primeiro_acesso'))
    return render_template('index.html')


@app.route('/consulta')
@login_required
def consulta():
    return render_template('consulta.html')


# --- MÓDULO PRODUÇÃO ---

@app.route('/producao')
@login_required
def producao_index():
    return render_template('producao_index.html')


@app.route('/producao/cirurgica')
@login_required
def producao_cirurgica():
    return render_template('producao.html')


# --- MÓDULO MÉDICOS ---

@app.route('/medicos')
@login_required
def medicos_index():
    return render_template('medicos_index.html')


@app.route('/medicos/cadastro')
@login_required
def medicos_cadastro():
    return render_template('medicos.html')


@app.route('/medicos/estatisticas')
@login_required
def medicos_estatisticas():
    return render_template('medicos_stats.html')


# --- MÓDULO AMBULATORIAL ---

@app.route('/ambulatorial')
@login_required
def ambulatorial_index():
    return render_template('ambulatorial_index.html')


@app.route('/ambulatorial/robo')
@login_required
def ambulatorial_robo():
    return render_template('amb_robo.html')


@app.route('/ambulatorial/visualizar')
@login_required
def ambulatorial_visualizar():
    return render_template('amb_visualizacao_index.html')


@app.route('/ambulatorial/visualizar/dashboard')
@login_required
def ambulatorial_dashboard():
    return "<h1>Dashboard em construção...</h1><a href='/ambulatorial/visualizar'>Voltar</a>"


@app.route('/ambulatorial/visualizar/tabelas')
@login_required
def ambulatorial_tabelas():
    return render_template('amb_tabelas.html')


@app.route('/ambulatorial/manual')
@login_required
def ambulatorial_manual_page():
    return render_template('amb_manual.html')


# --- MÓDULO EMPRESAS ---

@app.route('/empresas')
@login_required
def empresas_index():
    return render_template('empresas_index.html')


@app.route('/empresas/cadastro')
@login_required
def empresas_cadastro_menu():
    return render_template('empresas_cadastro_menu.html')


@app.route('/empresas/cadastro/automatico')
@login_required
def empresas_cadastro_automatico():
    """Renderiza a página de cadastro automático via PDF"""
    return render_template('empresas_cadastro_auto.html')


# Lista de Contratos
@app.route('/empresas/contratos')
@login_required
def empresas_contratos():
    conn = get_cadastro_conn()
    cursor = conn.cursor()

    # Busca contratos + nome da empresa (JOIN)
    try:
        cursor.execute("""
                       SELECT c.*, e.razao_social, e.arquivo_contrato
                       FROM contratos c
                                JOIN empresas e ON c.empresa_id = e.empresa_id
                       WHERE c.ativo = 1
                       ORDER BY c.servico ASC
                       """)
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Erro SQL em /empresas/contratos: {e}")
        rows = []

    conn.close()

    contratos_processados = []
    hoje = date.today()

    for row in rows:
        c = dict(row)

        data_inicio = parse_data_banco(c['data_contratacao'])
        vigencia = int(c['vigencia_meses']) if c['vigencia_meses'] else 0

        if data_inicio:
            data_fim = add_months(data_inicio, vigencia)
            delta = data_fim - hoje
            dias_restantes = delta.days

            if dias_restantes < 0:
                tempo_str = "Vencido"
                alerta = True
            else:
                anos = dias_restantes // 365
                resto_anos = dias_restantes % 365
                meses = resto_anos // 30
                dias = resto_anos % 30

                partes = []
                if anos > 0: partes.append(f"{anos} ano(s)")
                if meses > 0: partes.append(f"{meses} mês(es)")
                if dias > 0: partes.append(f"{dias} dia(s)")

                tempo_str = ", ".join(partes) if partes else "Vence hoje"
                alerta = dias_restantes < 180

            c['data_inicio_fmt'] = data_inicio.strftime('%d/%m/%Y')
            c['data_vencimento'] = data_fim.strftime('%d/%m/%Y')
            c['tempo_restante'] = tempo_str
            c['alerta'] = alerta
        else:
            c['data_inicio_fmt'] = "N/D"
            c['data_vencimento'] = "N/D"
            c['tempo_restante'] = "Data Inválida"
            c['alerta'] = False

        contratos_processados.append(c)

    return render_template('empresas_contratos.html', contratos=contratos_processados)


# Edição de Contratos
@app.route('/empresas/contratos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def empresas_contratos_editar(id):
    conn = get_cadastro_conn()
    cursor = conn.cursor()

    if request.method == 'POST':
        try:
            servico = request.form.get('servico')
            quantidade = request.form.get('quantidade')
            valor = request.form.get('valor')
            data_inicio = request.form.get('data_contratacao')
            vigencia = request.form.get('vigencia')

            cursor.execute("""
                           UPDATE contratos
                           SET servico          = ?,
                               quantidade       = ?,
                               valor_unitario   = ?,
                               data_contratacao = ?,
                               vigencia_meses   = ?
                           WHERE id = ?
                           """, (servico, quantidade, valor, data_inicio, vigencia, id))
            conn.commit()
            flash('Contrato atualizado com sucesso!', 'success')
            return redirect(url_for('empresas_contratos'))
        except Exception as e:
            flash(f'Erro ao atualizar: {e}', 'error')

    cursor.execute("""
                   SELECT c.*, e.razao_social
                   FROM contratos c
                            JOIN empresas e ON c.empresa_id = e.empresa_id
                   WHERE c.id = ?
                   """, (id,))
    contrato = cursor.fetchone()
    conn.close()

    if not contrato:
        flash('Contrato não encontrado.', 'error')
        return redirect(url_for('empresas_contratos'))

    return render_template('empresas_contrato_editar.html', contrato=dict(contrato))


@app.route('/empresas/upload_auto', methods=['POST'])
@login_required
def empresas_upload_auto():
    if 'file' not in request.files: return jsonify({'success': False, 'message': 'Sem arquivo'})
    file = request.files['file']
    try:
        filename = secure_filename(file.filename)
        timestamp = int(datetime.now().timestamp())
        unique_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        dados = extrair_dados_contrato(filepath)
        return jsonify({'success': True, 'data': dados, 'filename': unique_filename})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


def extrair_dados_contrato(filepath): return extrair_dados_pdf(filepath)


@app.route('/empresas/salvar_auto', methods=['POST'])
@login_required
def empresas_salvar_auto():
    try:
        data = request.get_json()
        usuario = current_user.email
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        empresa_uuid = str(uuid.uuid4())
        conn = get_cadastro_conn()

        conn.execute(
            "INSERT INTO empresas (empresa_id, razao_social, cnpj, objeto_contrato, data_contratacao, ativo, arquivo_contrato, usuario_cadastro, data_cadastro) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (empresa_uuid, data['razao_social'], data['cnpj'], "Prestação de Serviços Médicos (Contrato Automático)",
             data['data_contratacao'], 1, data['filename'], usuario, ts))

        for item in data['itens']:
            valor_limpo = str(item['valor']).replace('R$', '').replace('.', '').replace(',', '.').strip()
            try:
                val_float = float(valor_limpo)
            except:
                val_float = 0.0
            try:
                qtd_int = int(str(item['quantidade']).replace('.', ''))
            except:
                qtd_int = 0
            try:
                vig_int = int(data['vigencia_meses'])
            except:
                vig_int = 0

            conn.execute(
                "INSERT INTO contratos (empresa_id, servico, quantidade, valor_unitario, data_contratacao, vigencia_meses, ativo, usuario_cadastro, data_cadastro) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (empresa_uuid, item['servico'], qtd_int, val_float, data['data_contratacao'], vig_int, 1, usuario, ts))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Cadastro realizado com sucesso!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao salvar: {str(e)}'})


@app.route('/empresas/cadastro/manual', methods=['GET', 'POST'])
@login_required
def empresas_cadastro_manual():
    if request.method == 'POST':
        try:
            razao_social = request.form.get('razao_social')
            cnpj = request.form.get('cnpj')
            ativo = request.form.get('ativo')
            data_cadastro = request.form.get('data_cadastro')
            data_inativacao = request.form.get('data_inativacao')
            servicos = request.form.get('servicos')
            filename = None
            if 'contrato_pdf' in request.files:
                file = request.files['contrato_pdf']
                if file and file.filename != '':
                    fname = f"{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                    filename = fname

            empresa_uuid = str(uuid.uuid4())
            conn = get_cadastro_conn()

            conn.execute("""
                         INSERT INTO empresas (empresa_id, razao_social, cnpj, objeto_contrato, data_contratacao, ativo,
                                               data_inativacao, arquivo_contrato, usuario_cadastro)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                         """,
                         (empresa_uuid, razao_social, cnpj, servicos, data_cadastro, ativo, data_inativacao, filename,
                          current_user.email))

            # Cria um contrato genérico vinculado
            conn.execute("""
                         INSERT INTO contratos (empresa_id, servico, quantidade, valor_unitario, data_contratacao,
                                                vigencia_meses, ativo, usuario_cadastro)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                         """, (empresa_uuid, servicos or "Contrato Geral", 0, 0.0, data_cadastro, 12, ativo,
                               current_user.email))

            conn.commit()
            conn.close()
            flash('Empresa cadastrada com sucesso!', 'success')
            return redirect(url_for('empresas_index'))
        except Exception as e:
            flash(f'Erro ao salvar: {str(e)}', 'error')
    return render_template('empresas_manual.html')


@app.route('/download/contrato/<filename>')
@login_required
def download_contrato(filename):
    filename = secure_filename(filename)
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)


# --- ROTAS DE USUÁRIOS ---
@app.route('/configuracoes/usuarios', methods=['GET', 'POST'])
@login_required
def cadastro_usuario():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome');
            sexo = request.form.get('sexo');
            drt = request.form.get('drt')
            celular = request.form.get('celular');
            ramal = request.form.get('ramal');
            email = request.form.get('email');
            nivel = request.form.get('nivel')
            senha_inicial = generate_password_hash(drt)
            conn = get_cadastro_conn()
            conn.execute(
                "INSERT INTO usuarios (nome_completo, sexo, drt, celular, ramal, email, nivel_acesso, senha_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (nome, sexo, drt, celular, ramal, email, nivel, senha_inicial))
            conn.commit();
            conn.close()
            flash('Usuário cadastrado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash('Erro: Este e-mail já está cadastrado.', 'error')
        except Exception as e:
            flash(f'Erro ao cadastrar: {str(e)}', 'error')
    return render_template('cadastro_usuario.html')


# --- LÓGICA DE EXTRAÇÃO DE CONTRATO (PDF) ---
def extrair_dados_pdf(filepath):
    dados = {'razao_social': '', 'cnpj': '', 'objeto': '', 'data': '', 'escopo': []}
    try:
        with pdfplumber.open(filepath) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text: full_text += text + "\n"
                tables = page.extract_tables()
                for table in tables:
                    header_idx = -1
                    for i, row in enumerate(table):
                        row_str = " ".join([str(c).lower() for c in row if c])
                        if "especialidade" in row_str and "valor" in row_str:
                            header_idx = i;
                            break
                    if header_idx != -1:
                        for row in table[header_idx + 1:]:
                            row_clean = [str(c).replace('\n', ' ').strip() if c else '' for c in row]
                            if "valor mensal" in str(row_clean[0]).lower() or not any(row_clean): continue
                            try:
                                servico = row_clean[2];
                                qtd = row_clean[6]
                                if not qtd.isdigit(): qtd = re.sub(r'\D', '', qtd) or '0'
                                valor_str = next((c for c in row_clean if 'R$' in c), '0')
                                if servico and len(servico) > 3: dados['escopo'].append(
                                    {'servico': servico, 'quantidade': qtd, 'valor': valor_str})
                            except:
                                pass
            match_rs = re.search(r'Pelo presente,\s*(.*?),\s*inscrito', full_text, re.IGNORECASE)
            if match_rs: dados['razao_social'] = match_rs.group(1).replace('\n', ' ').strip().upper()
            match_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', full_text)
            if match_cnpj: dados['cnpj'] = match_cnpj.group(0)
            match_61 = re.search(r'6\.1\s+.*?(?=\n|6\.2)', full_text, re.DOTALL)
            if match_61:
                texto_61 = match_61.group(0)
                match_meses = re.search(r'prazo de\s*(\d+)', texto_61)
                if match_meses: dados['vigencia_meses'] = match_meses.group(1)
                match_data = re.search(r'(\d{2}/\d{2}/\d{4})', texto_61)
                if match_data: dados['data_contratacao'] = match_data.group(1)
    except Exception as e:
        print(f"Erro extração PDF: {e}")
    return dados


# --- APIS DE LEITURA E GRAVAÇÃO DE DADOS ---
@app.route('/ambulatorial/manual/analisar', methods=['POST'])
@login_required
def ambulatorial_analisar():
    if 'file' not in request.files: return jsonify({'success': False, 'message': 'Nenhum arquivo enviado'})
    file = request.files['file']
    if file.filename == '': return jsonify({'success': False, 'message': 'Arquivo não selecionado'})
    try:
        filename = secure_filename(file.filename);
        unique_filename = f"{int(datetime.now().timestamp())}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename);
        file.save(filepath)
        ext = filename.rsplit('.', 1)[1].lower()
        df_meta = None
        if ext == 'csv':
            try:
                df_meta = pd.read_csv(filepath, header=None, nrows=5, sep=';', encoding='latin1')
            except:
                df_meta = pd.read_csv(filepath, header=None, nrows=5, sep=',', encoding='latin1')
        else:
            try:
                df_meta = pd.read_excel(filepath, header=None, nrows=5)
            except:
                df_meta = pd.read_html(filepath, decimal=',', thousands='.', header=None)[0].iloc[:5]
        val_a3 = str(df_meta.iloc[2, 0]).strip()
        val_f3 = "Data não encontrada"
        if df_meta.shape[1] > 5:
            val_f3 = str(df_meta.iloc[2, 5]).strip()
        else:
            for c in range(df_meta.shape[1]):
                v = str(df_meta.iloc[2, c])
                if " de " in v and any(char.isdigit() for char in v): val_f3 = v; break

        target_table = ""
        if 'consulta' in val_a3.lower():
            target_table = "producao_amb"
        elif 'exame' in val_a3.lower():
            target_table = "producao_exame"

        if target_table == "": os.remove(filepath); return jsonify(
            {'success': False, 'message': f'Tipo desconhecido: {val_a3}'})
        return jsonify(
            {'success': True, 'confirmation_required': True, 'filename': unique_filename, 'tipo_arquivo': val_a3,
             'mes_ano': val_f3})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/ambulatorial/manual/confirmar', methods=['POST'])
@login_required
def ambulatorial_confirmar():
    data = request.get_json();
    filename = data.get('filename')
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath): return jsonify({'success': False, 'message': 'Arquivo expirou.'})
    try:
        ext = filename.rsplit('.', 1)[1].lower()
        df_meta = None
        if ext == 'csv':
            try:
                df_meta = pd.read_csv(filepath, header=None, nrows=5, sep=';', encoding='latin1')
            except:
                df_meta = pd.read_csv(filepath, header=None, nrows=5, sep=',', encoding='latin1')
        else:
            try:
                df_meta = pd.read_excel(filepath, header=None, nrows=5)
            except:
                df_meta = pd.read_html(filepath, decimal=',', thousands='.', header=None)[0].iloc[:5]

        val_a3 = str(df_meta.iloc[2, 0]).strip()
        val_f3 = ""
        if df_meta.shape[1] > 5: val_f3 = str(df_meta.iloc[2, 5]).strip()
        if not val_f3 or " de " not in val_f3:
            for c in range(df_meta.shape[1]):
                v = str(df_meta.iloc[2, c])
                if " de " in v: val_f3 = v; break

        tabela_destino = "producao_amb" if 'consulta' in val_a3.lower() else "producao_exame"
        try:
            partes = val_f3.lower().split(' de '); mes_arquivo, ano_arquivo = partes[0].capitalize(), int(partes[1])
        except:
            mes_arquivo, ano_arquivo = val_f3, 0

        df_preview = None
        if ext == 'csv':
            try:
                df_preview = pd.read_csv(filepath, header=None, nrows=15, sep=';', encoding='latin1')
            except:
                df_preview = pd.read_csv(filepath, header=None, nrows=15, sep=',', encoding='latin1')
        else:
            try:
                df_preview = pd.read_excel(filepath, header=None, nrows=15)
            except:
                df_preview = pd.read_html(filepath, decimal=',', thousands='.', header=None)[0].iloc[:15]

        header_idx = -1
        for idx, row in df_preview.iterrows():
            row_str = str(row.values).lower()
            if 'especialidade' in row_str and 'oferta' in row_str: header_idx = idx; break
        if header_idx == -1: raise Exception("Cabeçalho não encontrado")

        if ext == 'csv':
            df_dados = pd.read_csv(filepath, header=header_idx, sep=';', encoding='latin1') if ';' in open(filepath,
                                                                                                           encoding='latin1').read() else pd.read_csv(
                filepath, header=header_idx, sep=',', encoding='latin1')
        else:
            try:
                df_dados = pd.read_excel(filepath, header=header_idx)
            except:
                df_dados = pd.read_html(filepath, decimal=',', thousands='.', header=header_idx)[0]
        if df_dados.shape[1] < 4: raise Exception("Menos de 4 colunas encontradas.")
        df_trabalho = df_dados.iloc[:, :4].copy()
        df_trabalho.columns = ['especialidade', 'oferta', 'agendado', 'realizado']
        df_trabalho = df_trabalho.dropna(how='all')
        conn = get_amb_conn()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        usuario = current_user.email
        registros = 0
        for _, row in df_trabalho.iterrows():
            esp = str(row['especialidade']).strip()
            if not esp or esp.lower() in ['nan', 'total', 'especialidade']: continue

            def safe_int(v):
                try:
                    return int(float(str(v).replace('.', '').replace(',', '.')))
                except:
                    return 0

            oferta, agendado, realizado = safe_int(row['oferta']), safe_int(row['agendado']), safe_int(row['realizado'])
            conn.execute(
                f"INSERT INTO {tabela_destino} (especialidade, oferta, agendado, realizado, mes, ano, usuario, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (esp, oferta, agendado, realizado, mes_arquivo, ano_arquivo, current_user.email, timestamp))
            registros += 1
        conn.commit();
        conn.close();
        os.remove(filepath)
        return jsonify({'success': True, 'message': f'Sucesso! {registros} registros.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# APIs de Produção (Mantidas)
@app.route('/api/search_procedimento')
@login_required
def search_procedimento():
    term = request.args.get('term', '')
    if len(term) < 3: return jsonify([])
    conn = get_producao_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT nome, codigo_sigtap, valor_sigtap FROM procedimentos WHERE nome LIKE ? LIMIT 15",
                       ('%' + term + '%',))
    except:
        cursor.execute(
            "SELECT nome, codigo_sus as codigo_sigtap, valor_sigtap FROM procedimentos WHERE nome LIKE ? LIMIT 15",
            ('%' + term + '%',))
    res = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(res)


@app.route('/api/submit_producao', methods=['POST'])
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
        if row:
            cursor.execute(f"UPDATE producao SET {col_sql} = ? WHERE id = ?", (qtd, row['id']))
        else:
            cursor.execute(f"INSERT INTO producao (codigo_sigtap, {col_sql}) VALUES (?, ?)", (cod, qtd))
        conn.commit()
        return jsonify({'success': True, 'message': 'Salvo'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/producao_mensal', methods=['GET'])
@login_required
def get_producao_mensal():
    cod, mes = request.args.get('codigo_sigtap'), int(request.args.get('mes', 0))
    col = COLUNAS_MESES.get(mes)
    conn = get_producao_conn()
    col_sql = f'"{col}"' if col in ['set', 'out'] else col
    try:
        res = conn.execute(
            f"SELECT t.{col_sql} as q, p.nome, p.valor_sigtap FROM producao t JOIN procedimentos p ON t.codigo_sigtap = p.codigo_sigtap WHERE t.codigo_sigtap = ?",
            (cod,)).fetchone()
        if res: return jsonify({'encontrado': True, 'total': res['q'] or 0,
                                'valor_total_produzido': (res['q'] or 0) * (res['valor_sigtap'] or 0)})
        return jsonify({'encontrado': False})
    except:
        return jsonify({'encontrado': False})
    finally:
        conn.close()


@app.route('/api/historico', methods=['GET'])
@login_required
def get_historico():
    cod = request.args.get('codigo_sigtap')
    conn = get_producao_conn()
    cols = ", ".join([f't."{v}"' if v in ['set', 'out'] else f't.{v}' for v in COLUNAS_MESES.values()])
    res = conn.execute(f"SELECT {cols} FROM producao t WHERE t.codigo_sigtap = ?", (cod,)).fetchone()
    hist = [{'mes': m, 'total_producao': res[m - 1] or 0} for m in range(1, 13)] if res else []
    conn.close()
    return jsonify({'data': hist})


@app.route('/api/analise_ia', methods=['POST'])
@login_required
def analise_ia():
    if not GEMINI_API_KEY: return jsonify({'error': 'Sem chave API'}), 500
    data = request.get_json()
    try:
        res = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": f"Analise: {data}"}]}]})
        return jsonify({'markdown': res.json()['candidates'][0]['content']['parts'][0]['text']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/siresp/sync', methods=['POST'])
@login_required
def siresp_sync():
    def generate():
        yield json.dumps({"status": "info", "message": "Iniciando..."}) + "\n"
        yield json.dumps({"status": "success", "message": "Fim."}) + "\n"

    return app.response_class(generate(), mimetype='application/json')


@app.route('/api/ambulatorial/filtros', methods=['GET'])
@login_required
def get_filtros_ambulatorial():
    conn = get_amb_conn()
    try:
        filtros = {"especialidades": [], "meses": [], "anos": []}
        for c in ["especialidade", "mes", "ano"]:
            res = conn.execute(f"SELECT DISTINCT {c} FROM producao_amb ORDER BY {c}").fetchall()
            filtros[f"{c}s" if c != "mes" else "meses"] = [r[0] for r in res if r[0]]
        return jsonify(filtros)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/ambulatorial/dados', methods=['GET'])
@login_required
def get_dados_ambulatorial():
    esp, mes, ano = request.args.get('especialidade'), request.args.get('mes'), request.args.get('ano')
    conn = get_amb_conn()
    try:
        query = "SELECT * FROM producao_amb WHERE 1=1"
        params = []
        if esp and esp != "Todas": query += " AND especialidade = ?"; params.append(esp)
        if mes and mes != "Todos": query += " AND mes = ?"; params.append(mes)
        if ano and ano != "Todos": query += " AND ano = ?"; params.append(ano)
        rows = conn.execute(query, params).fetchall()

        resultados = []
        for row in rows:
            d = dict(row)
            oferta, agendado, realizado = d.get('oferta', 0) or 0, d.get('agendado', 0) or 0, d.get('realizado', 0) or 0
            d['taxa_absenteismo'] = round((1 - (realizado / agendado)) * 100, 2) if agendado > 0 else 0.0
            d['taxa_perda_primaria'] = round((1 - (agendado / oferta)) * 100, 2) if oferta > 0 else 0.0
            resultados.append(d)
        return jsonify(resultados)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/medicos/stats', methods=['GET'])
@login_required
def medicos_stats_api():
    conn = get_medicos_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT dn, sexo, naturalidade, estado_natural, cidade_res FROM medicos")
        rows = cursor.fetchall()
        total = len(rows)
        sexo = {'Masculino': 0, 'Feminino': 0, 'Outros': 0}
        faixa = {'< 30 anos': 0, '30-39 anos': 0, '40-49 anos': 0, '50-59 anos': 0, '60+ anos': 0, 'N/D': 0}
        origem, residencia = {}, {}

        for row in rows:
            s = str(row['sexo']).strip()
            if s == '1':
                sexo['Feminino'] += 1
            elif s == '0':
                sexo['Masculino'] += 1
            else:
                sexo['Outros'] += 1

            idade = calcular_idade(row['dn'])
            if idade is None:
                faixa['N/D'] += 1
            elif idade < 30:
                faixa['< 30 anos'] += 1
            elif idade < 40:
                faixa['30-39 anos'] += 1
            elif idade < 50:
                faixa['40-49 anos'] += 1
            elif idade < 60:
                faixa['50-59 anos'] += 1
            else:
                faixa['60+ anos'] += 1

            nat = str(row['naturalidade']).strip().upper()
            if nat and nat != 'NONE': origem[nat] = origem.get(nat, 0) + 1

            res = str(row['cidade_res']).strip().upper()
            if res and res != 'NONE': residencia[res] = residencia.get(res, 0) + 1

        top_origem = dict(sorted(origem.items(), key=lambda i: i[1], reverse=True)[:10])
        top_residencia = dict(sorted(residencia.items(), key=lambda i: i[1], reverse=True)[:10])

        return jsonify(
            {'total': total, 'sexo': sexo, 'faixa_etaria': faixa, 'origem': top_origem, 'residencia': top_residencia})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)