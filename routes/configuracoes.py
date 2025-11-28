from flask import Blueprint, render_template, request, flash
from flask_login import login_required
from database import get_cadastro_conn
from werkzeug.security import generate_password_hash
import sqlite3

configuracoes_bp = Blueprint('configuracoes', __name__)

@configuracoes_bp.route('/configuracoes/usuarios', methods=['GET', 'POST'])
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
            conn.execute("INSERT INTO usuarios (nome_completo, sexo, drt, celular, ramal, email, nivel_acesso, senha_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (nome, sexo, drt, celular, ramal, email, nivel, senha_inicial))
            conn.commit()
            conn.close()
            flash('Usuário cadastrado com sucesso!', 'success')
        except sqlite3.IntegrityError: flash('Erro: Este e-mail já está cadastrado.', 'error')
        except Exception as e: flash(f'Erro ao cadastrar: {str(e)}', 'error')
    return render_template('cadastro_usuario.html')