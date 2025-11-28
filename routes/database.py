import sqlite3
import os

# Configuração de Caminhos (ajustado para garantir caminho absoluto relativo ao arquivo)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, 'db')

DB_PRODUCAO = os.path.join(DB_FOLDER, 'producao_cirurgica.db')
DB_MEDICOS = os.path.join(DB_FOLDER, 'medicos.db')
DB_AMB = os.path.join(DB_FOLDER, 'amb.db')
DB_CADASTRO = os.path.join(DB_FOLDER, 'cadastro.db')

geral_bp = Blueprint('geral', __name__)

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