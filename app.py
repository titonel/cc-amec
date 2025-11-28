import os
import sys

# Adiciona o diretório atual (onde está app.py) ao sys.path
# Isso garante que 'database.py' e a pasta 'routes' sejam encontrados
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from flask import Flask
from flask_login import LoginManager
from database import get_cadastro_conn  # Agora a importação deve funcionar
from models import User

# Importação dos Blueprints
from routes.auth import auth_bp
from routes.main import main_bp
from routes.medicos import medicos_bp
from routes.empresas import empresas_bp
from routes.producao import producao_bp
from routes.ambulatorial import ambulatorial_bp
from routes.configuracoes import configuracoes_bp
from routes.geral import geral_bp

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')  # Usando caminho absoluto
app.config['SECRET_KEY'] = 'chave_super_secreta_amec_2025'

# Garante pastas
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db_dir = os.path.join(BASE_DIR, 'db')
if not os.path.exists(db_dir): os.makedirs(db_dir)

# Configuração Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = "Por favor, faça login para acessar o sistema."


@login_manager.user_loader
def load_user(user_id):
    conn = get_cadastro_conn()
    # Verifica se a tabela existe antes de tentar buscar usuário
    try:
        row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        conn.close()

    if row: return User(row['id'], row['nome_completo'], row['email'], row['nivel_acesso'], row['primeiro_acesso'])
    return None


# Registro de Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(medicos_bp)
app.register_blueprint(empresas_bp)
app.register_blueprint(producao_bp)
app.register_blueprint(ambulatorial_bp)
app.register_blueprint(configuracoes_bp)
app.register_blueprint(geral_bp)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)