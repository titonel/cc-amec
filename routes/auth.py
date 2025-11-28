from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_cadastro_conn
from models import User  # Importaremos User de um arquivo separado ou definiremos aqui se for simples

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')

        conn = get_cadastro_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        user_data = cursor.fetchone()
        conn.close()

        if user_data and check_password_hash(user_data['senha_hash'], senha):
            # Import User aqui para evitar ciclo ou defina em models.py
            from models import User
            user_obj = User(
                id=user_data['id'],
                nome=user_data['nome_completo'],
                email=user_data['email'],
                nivel_acesso=user_data['nivel_acesso'],
                primeiro_acesso=user_data['primeiro_acesso']
            )
            login_user(user_obj)

            if user_data['primeiro_acesso'] == 1:
                return redirect(url_for('auth.primeiro_acesso'))

            return redirect(url_for('main.index'))
        else:
            flash('Email ou senha inválidos.', 'error')

    return render_template('login.html')


@auth_bp.route('/primeiro_acesso', methods=['GET', 'POST'])
@login_required
def primeiro_acesso():
    if current_user.primeiro_acesso == 0:
        return redirect(url_for('main.index'))

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

            current_user.primeiro_acesso = 0
            flash('Senha alterada com sucesso!', 'success')
            return redirect(url_for('main.index'))

    return render_template('primeiro_acesso.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))