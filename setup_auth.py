import sqlite3
import os
import shutil
from werkzeug.security import generate_password_hash

# Configuração de Caminhos
DB_FOLDER = 'db'
ARQUIVOS_DB = ['medicos.db', 'producao_cirurgica.db', 'amb.db']
DB_CADASTRO = os.path.join(DB_FOLDER, 'cadastro.db')

def setup_environment():
    print("--- Iniciando Configuração de Ambiente e Autenticação ---")

    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    # 1. Configurar Banco de Cadastro
    conn = sqlite3.connect(DB_CADASTRO)
    cursor = conn.cursor()

    # Tabela Usuários (Mantida - Cuidado: se quiser resetar usuarios, descomente a linha abaixo)
    # cursor.execute("DROP TABLE IF EXISTS usuarios")
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

    # --- ATUALIZAÇÃO DO SCHEMA ---
    # Remove tabelas antigas para garantir a nova estrutura
    print("Recriando tabelas 'empresas' e 'contratos'...")
    cursor.execute("DROP TABLE IF EXISTS empresas")
    cursor.execute("DROP TABLE IF EXISTS contratos")

    # Tabela Empresas (Atualizada com data_contratacao)
    cursor.execute("""
    CREATE TABLE empresas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        razao_social TEXT,
        cnpj TEXT,
        objeto_contrato TEXT,
        data_contratacao TEXT,
        ativo INTEGER DEFAULT 1,
        data_inativacao TEXT,
        arquivo_contrato TEXT,
        escopo_json TEXT,
        usuario_cadastro TEXT,
        data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Tabela Contratos (Nova)
    cursor.execute("""
    CREATE TABLE contratos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER,
        servico TEXT,
        quantidade INTEGER,
        valor_unitario REAL,
        data_contratacao TEXT,
        vigencia_meses INTEGER,
        ativo INTEGER DEFAULT 1,
        usuario_cadastro TEXT,
        data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(empresa_id) REFERENCES empresas(id)
    )
    """)

    # Bootstrap Admin (se necessário)
    cursor.execute("SELECT count(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        pass_hash = generate_password_hash("123456")
        cursor.execute("INSERT INTO usuarios (nome_completo, sexo, drt, celular, email, nivel_acesso, senha_hash) VALUES (?,?,?,?,?,?,?)",
                       ("Admin", "M", "0000", "0000", "admin@amecaragua.org.br", "Gerente", pass_hash))
        # Adiciona segundo usuário solicitado anteriormente
        cursor.execute("INSERT INTO usuarios (nome_completo, sexo, drt, celular, email, nivel_acesso, senha_hash) VALUES (?,?,?,?,?,?,?)",
                       ("Saulo Bastos", "M", "11111", "0000", "saulo.bastos@amecaragua.org.br", "Gerente", pass_hash))

    conn.commit()
    conn.close()
    print("Banco de dados 'cadastro.db' reconfigurado com sucesso.")

if __name__ == '__main__':
    setup_environment()