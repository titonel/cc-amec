from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def index():
    if current_user.primeiro_acesso == 1: return redirect(url_for('auth.primeiro_acesso'))
    return render_template('index.html')

@main_bp.route('/consulta')
@login_required
def consulta():
    return render_template('consulta.html')