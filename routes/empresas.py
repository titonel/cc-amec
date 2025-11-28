from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, send_from_directory, current_app
from flask_login import login_required, current_user
from database import get_cadastro_conn
from werkzeug.utils import secure_filename
from datetime import datetime, date
import pdfplumber
import re
import os
import json
import uuid

empresas_bp = Blueprint('empresas', __name__)

def parse_data_banco(data_str):
    if not data_str: return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try: return datetime.strptime(data_str, fmt).date()
        except ValueError: pass
    return None

def add_months(source_date, months):
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, [31, 29 if year % 4 == 0 and not year % 100 == 0 or year % 400 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month-1])
    return date(year, month, day)

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
                            header_idx = i; break
                    if header_idx != -1:
                        for row in table[header_idx+1:]:
                            row_clean = [str(c).replace('\n', ' ').strip() if c else '' for c in row]
                            if "valor mensal" in str(row_clean[0]).lower() or not any(row_clean): continue
                            try:
                                servico = row_clean[2]; qtd = row_clean[6]
                                if not qtd.isdigit(): qtd = re.sub(r'\D', '', qtd) or '0'
                                valor_str = next((c for c in row_clean if 'R$' in c), '0')
                                if servico and len(servico) > 3: dados['escopo'].append({'servico': servico, 'quantidade': qtd, 'valor': valor_str})
                            except: pass
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
    except Exception as e: print(f"Erro extração PDF: {e}")
    return dados

def extrair_dados_contrato(filepath): return extrair_dados_pdf(filepath)

@empresas_bp.route('/empresas')
@login_required
def index():
    return render_template('empresas_index.html')

@empresas_bp.route('/empresas/cadastro')
@login_required
def cadastro_menu():
    return render_template('empresas_cadastro_menu.html')

@empresas_bp.route('/empresas/cadastro/automatico')
@login_required
def cadastro_automatico():
    return render_template('empresas_cadastro_auto.html')

@empresas_bp.route('/empresas/contratos')
@login_required
def contratos():
    conn = get_cadastro_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT c.*, e.razao_social, e.arquivo_contrato 
            FROM contratos c 
            JOIN empresas e ON c.empresa_id = e.empresa_id 
            WHERE c.ativo = 1
            ORDER BY c.servico ASC
        """)
        rows = cursor.fetchall()
    except sqlite3.OperationalError: rows = []
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
            c['data_inicio_fmt'] = data_inicio.strftime('%d/%m/%Y')
            c['data_vencimento'] = data_fim.strftime('%d/%m/%Y')
            if dias_restantes < 0: c['tempo_restante'] = "Vencido"; c['alerta'] = True
            else:
                anos, r = divmod(dias_restantes, 365)
                meses, dias = divmod(r, 30)
                partes = []
                if anos: partes.append(f"{anos} ano(s)")
                if meses: partes.append(f"{meses} mês(es)")
                if dias: partes.append(f"{dias} dia(s)")
                c['tempo_restante'] = ", ".join(partes) if partes else "Vence hoje"
                c['alerta'] = dias_restantes < 180
        else:
            c.update({'data_inicio_fmt': "N/D", 'data_vencimento': "N/D", 'tempo_restante': "Data Inválida", 'alerta': False})
        contratos_processados.append(c)
    return render_template('empresas_contratos.html', contratos=contratos_processados)

@empresas_bp.route('/empresas/upload_auto', methods=['POST'])
@login_required
def upload_auto():
    if 'file' not in request.files: return jsonify({'success': False, 'message': 'Sem arquivo'})
    file = request.files['file']
    try:
        filename = secure_filename(file.filename)
        timestamp = int(datetime.now().timestamp())
        unique_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        dados = extrair_dados_contrato(filepath)
        return jsonify({'success': True, 'data': dados, 'filename': unique_filename})
    except Exception as e: return jsonify({'success': False, 'message': str(e)})

@empresas_bp.route('/empresas/salvar_auto', methods=['POST'])
@login_required
def salvar_auto():
    try:
        data = request.get_json()
        usuario = current_user.email
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        empresa_uuid = str(uuid.uuid4())
        conn = get_cadastro_conn()
        conn.execute("INSERT INTO empresas (empresa_id, razao_social, cnpj, objeto_contrato, data_contratacao, ativo, arquivo_contrato, usuario_cadastro, data_cadastro) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (empresa_uuid, data['razao_social'], data['cnpj'], "Prestação de Serviços Médicos (Contrato Automático)", data['data_contratacao'], 1, data['filename'], usuario, ts))
        for item in data['itens']:
            valor_limpo = str(item['valor']).replace('R$', '').replace('.', '').replace(',', '.').strip()
            try: val_float = float(valor_limpo)
            except: val_float = 0.0
            try: qtd_int = int(str(item['quantidade']).replace('.', ''))
            except: qtd_int = 0
            try: vig_int = int(data['vigencia_meses'])
            except: vig_int = 0
            conn.execute("INSERT INTO contratos (empresa_id, servico, quantidade, valor_unitario, data_contratacao, vigencia_meses, ativo, usuario_cadastro, data_cadastro) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (empresa_uuid, item['servico'], qtd_int, val_float, data['data_contratacao'], vig_int, 1, usuario, ts))
        conn.commit(); conn.close()
        return jsonify({'success': True, 'message': 'Cadastro realizado com sucesso!'})
    except Exception as e: return jsonify({'success': False, 'message': f'Erro ao salvar: {str(e)}'})

@empresas_bp.route('/empresas/cadastro/manual', methods=['GET', 'POST'])
@login_required
def cadastro_manual():
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
                    file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], fname))
                    filename = fname
            empresa_uuid = str(uuid.uuid4())
            conn = get_cadastro_conn()
            conn.execute("INSERT INTO empresas (empresa_id, razao_social, cnpj, objeto_contrato, data_contratacao, ativo, data_inativacao, arquivo_contrato, usuario_cadastro) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (empresa_uuid, razao_social, cnpj, servicos, data_cadastro, ativo, data_inativacao, filename, current_user.email))
            conn.execute("INSERT INTO contratos (empresa_id, servico, quantidade, valor_unitario, data_contratacao, vigencia_meses, ativo, usuario_cadastro) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (empresa_uuid, servicos or "Contrato Geral", 0, 0.0, data_cadastro, 12, ativo, current_user.email))
            conn.commit(); conn.close()
            flash('Empresa cadastrada com sucesso!', 'success')
            return redirect(url_for('empresas.index'))
        except Exception as e:
            flash(f'Erro ao salvar: {str(e)}', 'error')
    return render_template('empresas_manual.html')

@empresas_bp.route('/empresas/contratos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def contratos_editar(id):
    conn = get_cadastro_conn()
    cursor = conn.cursor()
    if request.method == 'POST':
        try:
            servico = request.form.get('servico')
            quantidade = request.form.get('quantidade')
            valor = request.form.get('valor')
            data_inicio = request.form.get('data_contratacao')
            vigencia = request.form.get('vigencia')
            cursor.execute("UPDATE contratos SET servico = ?, quantidade = ?, valor_unitario = ?, data_contratacao = ?, vigencia_meses = ? WHERE id = ?",
                           (servico, quantidade, valor, data_inicio, vigencia, id))
            conn.commit()
            flash('Contrato atualizado com sucesso!', 'success')
            return redirect(url_for('empresas.contratos'))
        except Exception as e: flash(f'Erro ao atualizar: {e}', 'error')
    cursor.execute("SELECT c.*, e.razao_social FROM contratos c JOIN empresas e ON c.empresa_id = e.empresa_id WHERE c.id = ?", (id,))
    contrato = cursor.fetchone()
    conn.close()
    if not contrato: flash('Contrato não encontrado.', 'error'); return redirect(url_for('empresas.contratos'))
    return render_template('empresas_contrato_editar.html', contrato=dict(contrato))