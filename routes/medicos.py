from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from database import get_medicos_conn
from datetime import datetime, date

medicos_bp = Blueprint('medicos', __name__)

def calcular_idade(data_nasc_str):
    try:
        if not data_nasc_str: return None
        nasc = datetime.strptime(data_nasc_str, "%Y-%m-%d").date()
        hoje = date.today()
        return hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
    except: return None

@medicos_bp.route('/medicos')
@login_required
def index():
    return render_template('medicos_index.html')

@medicos_bp.route('/medicos/cadastro')
@login_required
def cadastro():
    return render_template('medicos.html')

@medicos_bp.route('/medicos/estatisticas')
@login_required
def estatisticas():
    return render_template('medicos_stats.html')

# APIs
@medicos_bp.route('/api/medicos', methods=['GET'])
@login_required
def get_medicos():
    conn = get_medicos_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM medicos ORDER BY nome")
        medicos = [dict(row) for row in cursor.fetchall()]
        return jsonify(medicos)
    except Exception as e: return jsonify({'error': str(e)}), 500
    finally: conn.close()

@medicos_bp.route('/api/medicos', methods=['POST'])
@login_required
def add_medico():
    data = request.get_json()
    conn = get_medicos_conn()
    try:
        cols = ['nome', 'crm', 'dn', 'especialidade', 'nacionalidade', 'naturalidade', 'estado_natural', 'tel_ddd', 'tel_cel', 'email', 'cpf', 'rg', 'cep_res', 'end_res', 'num_res', 'comp_res', 'bairro_res', 'cidade_res', 'estado_res', 'ativo', 'inicio_ativ', 'fim_ativ', 'sexo']
        vals = [data.get(c, '') for c in cols]
        placeholders = ', '.join(['?'] * len(cols))
        conn.execute(f"INSERT INTO medicos ({', '.join(cols)}) VALUES ({placeholders})", vals)
        conn.commit()
        return jsonify({'success': True, 'message': 'Médico cadastrado!'})
    except Exception as e: return jsonify({'success': False, 'message': str(e)}), 500
    finally: conn.close()

@medicos_bp.route('/api/medicos/<int:id>', methods=['PUT'])
@login_required
def update_medico(id):
    data = request.get_json()
    conn = get_medicos_conn()
    try:
        cols = ['nome', 'crm', 'dn', 'especialidade', 'nacionalidade', 'naturalidade', 'estado_natural', 'tel_ddd', 'tel_cel', 'email', 'cpf', 'rg', 'cep_res', 'end_res', 'num_res', 'comp_res', 'bairro_res', 'cidade_res', 'estado_res', 'ativo', 'inicio_ativ', 'fim_ativ', 'sexo']
        updates = ', '.join([f"{c} = ?" for c in cols])
        vals = [data.get(c, '') for c in cols]; vals.append(id)
        conn.execute(f"UPDATE medicos SET {updates} WHERE id = ?", vals)
        conn.commit()
        return jsonify({'success': True, 'message': 'Atualizado!'})
    except Exception as e: return jsonify({'success': False, 'message': str(e)}), 500
    finally: conn.close()

@medicos_bp.route('/api/especialidades_amec', methods=['GET'])
@login_required
def get_especialidades_amec():
    conn = get_medicos_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT especialidade FROM especialidades_amec ORDER BY especialidade ASC")
        lista = [row['especialidade'] for row in cursor.fetchall()]
        return jsonify(lista)
    except Exception as e: return jsonify([]), 500
    finally: conn.close()

@medicos_bp.route('/api/medicos/stats', methods=['GET'])
@login_required
def stats_api():
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
            if s == '1': sexo['Feminino'] += 1
            elif s == '0': sexo['Masculino'] += 1
            else: sexo['Outros'] += 1
            idade = calcular_idade(row['dn'])
            if idade is None: faixa['N/D'] += 1
            elif idade < 30: faixa['< 30 anos'] += 1
            elif idade < 40: faixa['30-39 anos'] += 1
            elif idade < 50: faixa['40-49 anos'] += 1
            elif idade < 60: faixa['50-59 anos'] += 1
            else: faixa['60+ anos'] += 1
            nat = str(row['naturalidade']).strip().upper()
            if nat and nat != 'NONE': origem[nat] = origem.get(nat, 0) + 1
            res = str(row['cidade_res']).strip().upper()
            if res and res != 'NONE': residencia[res] = residencia.get(res, 0) + 1
        top_origem = dict(sorted(origem.items(), key=lambda i: i[1], reverse=True)[:10])
        top_residencia = dict(sorted(residencia.items(), key=lambda i: i[1], reverse=True)[:10])
        return jsonify({'total': total, 'sexo': sexo, 'faixa_etaria': faixa, 'origem': top_origem, 'residencia': top_residencia})
    except Exception as e: return jsonify({'error': str(e)}), 500
    finally: conn.close()