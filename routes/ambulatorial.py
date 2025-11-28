from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from database import get_amb_conn
from werkzeug.utils import secure_filename
import pandas as pd
import os
import json
from datetime import datetime

ambulatorial_bp = Blueprint('ambulatorial', __name__)


@ambulatorial_bp.route('/ambulatorial')
@login_required
def index():
    return render_template('ambulatorial_index.html')


@ambulatorial_bp.route('/ambulatorial/robo')
@login_required
def robo():
    return render_template('amb_robo.html')


@ambulatorial_bp.route('/ambulatorial/visualizar')
@login_required
def visualizar():
    return render_template('amb_visualizacao_index.html')


@ambulatorial_bp.route('/ambulatorial/visualizar/dashboard')
@login_required
def dashboard():
    return "<h1>Dashboard em construção...</h1><a href='/ambulatorial/visualizar'>Voltar</a>"


@ambulatorial_bp.route('/ambulatorial/visualizar/tabelas')
@login_required
def tabelas():
    return render_template('amb_tabelas.html')


@ambulatorial_bp.route('/ambulatorial/manual')
@login_required
def manual_page():
    return render_template('amb_manual.html')


@ambulatorial_bp.route('/api/siresp/sync', methods=['POST'])
@login_required
def siresp_sync():
    def generate():
        yield json.dumps({"status": "info", "message": "Iniciando..."}) + "\n"
        yield json.dumps({"status": "success", "message": "Fim."}) + "\n"

    return current_app.response_class(generate(), mimetype='application/json')


@ambulatorial_bp.route('/api/ambulatorial/filtros', methods=['GET'])
@login_required
def get_filtros():
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


@ambulatorial_bp.route('/api/ambulatorial/dados', methods=['GET'])
@login_required
def get_dados():
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


@ambulatorial_bp.route('/ambulatorial/manual/analisar', methods=['POST'])
@login_required
def analisar():
    if 'file' not in request.files: return jsonify({'success': False, 'message': 'Nenhum arquivo enviado'})
    file = request.files['file']
    try:
        filename = secure_filename(file.filename);
        unique_filename = f"{int(datetime.now().timestamp())}_{filename}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename);
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


@ambulatorial_bp.route('/ambulatorial/manual/confirmar', methods=['POST'])
@login_required
def confirmar():
    data = request.get_json();
    filename = data.get('filename')
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
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