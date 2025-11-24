import sqlite3
import os
import shutil
from werkzeug.security import generate_password_hash

# Configuração de Caminhos
DB_FOLDER = 'db'
ARQUIVOS_DB = ['medicos.db', 'producao_cirurgica.db', 'amb.db'] # Adicionei amb.db para manter organização
DB_CADASTRO = os.path.join(DB_FOLDER, 'cadastro.db')

def setup_environment():
    print("--- Iniciando Configuração de Ambiente e Autenticação ---")

    # 1. Criar pasta 'db' se não existir
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        print(f"Pasta '{DB_FOLDER}' criada.")

    # 2. Mover bancos de dados existentes
    for db_file in ARQUIVOS_DB:
        if os.path.exists(db_file):
            destino = os.path.join(DB_FOLDER, db_file)
            # Evita sobrescrever se já existir no destino
            if not os.path.exists(destino):
                shutil.move(db_file, destino)
                print(f"Arquivo '{db_file}' movido para '{DB_FOLDER}/'.")
            else:
                print(f"Arquivo '{db_file}' já existe em '{DB_FOLDER}/'. Mantendo original (ou remova manualmente o da raiz).")
                # Opcional: remover o da raiz se já existe no destino para limpar
                # os.remove(db_file) 

    # 3. Criar banco de dados de Cadastro (Usuários)
    conn = sqlite3.connect(DB_CADASTRO)
    cursor = conn.cursor()

    # Tabela de Usuários
    # drt é usado como senha inicial, mas armazenamos a senha_hash real para login
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_completo TEXT NOT NULL,
        sexo TEXT,
        drt TEXT NOT NULL,
        celular TEXT,
        ramal TEXT,
        email TEXT UNIQUE NOT NULL,
        nivel_acesso TEXT NOT NULL,
        senha_hash TEXT NOT NULL,
        primeiro_acesso INTEGER DEFAULT 1
    )
    """)

    # Criar usuários padrão se a tabela estiver vazia (Bootstrap)
    cursor.execute("SELECT count(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        
        # Definição dos usuários iniciais
        usuarios_iniciais = [
            {
                "nome": "Administrador Geral",
                "sexo": "M",
                "drt": "00000",
                "celular": "00000",
                "email": "admin@amecaragua.org.br",
                "nivel": "Gerente"
            },
            {
                "nome": "Saulo Bastos",
                "sexo": "M",
                "drt": "11111", 
                "celular": "00000",
                "email": "saulo.bastos@amecaragua.org.br",
                "nivel": "Gerente"
            }
        ]
        
        # Gera o hash da senha padrão uma vez para usar nos inserts
        senha_padrao_hash = generate_password_hash("123456")

        for u in usuarios_iniciais:
            cursor.execute("""
                INSERT INTO usuarios (nome_completo, sexo, drt, celular, email, nivel_acesso, senha_hash, primeiro_acesso)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (u['nome'], u['sexo'], u['drt'], u['celular'], u['email'], u['nivel'], senha_padrao_hash, 1))
            print(f"Usuário criado: {u['email']} (Senha inicial: 123456)")

    conn.commit()
    conn.close()
    print("Banco de dados de cadastro configurado com sucesso.")

if __name__ == '__main__':
    setup_environment()