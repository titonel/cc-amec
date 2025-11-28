import sqlite3
import os
import shutil
import uuid
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

# Configuração de Caminhos
DB_FOLDER = 'db'
DB_CADASTRO = os.path.join(DB_FOLDER, 'cadastro.db')


def setup_environment():
    print("--- Iniciando Configuração de Ambiente e Autenticação ---")

    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    # ATENÇÃO: Remove o arquivo do banco para garantir schema novo
    if os.path.exists(DB_CADASTRO):
        try:
            os.remove(DB_CADASTRO)
            print(f"Banco antigo '{DB_CADASTRO}' removido para atualização de esquema.")
        except Exception as e:
            print(f"Erro ao remover banco antigo: {e}. Tente fechar o app Flask e rodar novamente.")
            return

    # Cria novo banco
    conn = sqlite3.connect(DB_CADASTRO)
    cursor = conn.cursor()

    print("Criando tabelas...")

    # Tabela Usuários
    cursor.execute("""
                   CREATE TABLE usuarios
                   (
                       id              INTEGER PRIMARY KEY AUTOINCREMENT,
                       nome_completo   TEXT        NOT NULL,
                       sexo            TEXT,
                       drt             TEXT        NOT NULL,
                       celular         TEXT,
                       ramal           TEXT,
                       email           TEXT UNIQUE NOT NULL,
                       nivel_acesso    TEXT        NOT NULL,
                       senha_hash      TEXT        NOT NULL,
                       primeiro_acesso INTEGER DEFAULT 1
                   )
                   """)

    # Tabela Empresas (Com UUID empresa_id)
    cursor.execute("""
                   CREATE TABLE empresas
                   (
                       id               INTEGER PRIMARY KEY AUTOINCREMENT,
                       empresa_id       TEXT UNIQUE, -- UUID
                       razao_social     TEXT,
                       cnpj             TEXT,
                       objeto_contrato  TEXT,
                       data_contratacao TEXT,
                       ativo            INTEGER   DEFAULT 1,
                       data_inativacao  TEXT,
                       arquivo_contrato TEXT,
                       escopo_json      TEXT,
                       usuario_cadastro TEXT,
                       data_cadastro    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                   )
                   """)

    # Tabela Contratos (Com UUID empresa_id)
    cursor.execute("""
                   CREATE TABLE contratos
                   (
                       id               INTEGER PRIMARY KEY AUTOINCREMENT,
                       empresa_id       TEXT, -- Chave estrangeira (UUID)
                       servico          TEXT,
                       quantidade       INTEGER,
                       valor_unitario   REAL,
                       data_contratacao TEXT,
                       vigencia_meses   INTEGER,
                       ativo            INTEGER   DEFAULT 1,
                       usuario_cadastro TEXT,
                       data_cadastro    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                       FOREIGN KEY (empresa_id) REFERENCES empresas (empresa_id)
                   )
                   """)

    # Bootstrap Admin
    pass_hash = generate_password_hash("123456")
    cursor.execute(
        "INSERT INTO usuarios (nome_completo, sexo, drt, celular, email, nivel_acesso, senha_hash) VALUES (?,?,?,?,?,?,?)",
        ("Admin", "M", "0000", "0000", "admin@amecaragua.org.br", "Gerente", pass_hash))
    cursor.execute(
        "INSERT INTO usuarios (nome_completo, sexo, drt, celular, email, nivel_acesso, senha_hash) VALUES (?,?,?,?,?,?,?)",
        ("Saulo Bastos", "M", "11111", "0000", "saulo.bastos@amecaragua.org.br", "Gerente", pass_hash))

    print("Usuários padrão criados.")

    # --- DADOS DE TESTE (MOCK) PARA CONTRATOS ---
    # Inserir uma empresa e um contrato de teste para validar a visualização
    mock_uuid = str(uuid.uuid4())
    hoje = datetime.now().strftime("%Y-%m-%d")
    data_inicio_teste = "2023-01-01"  # Data antiga para testar cálculo

    print("Inserindo dados de teste (Empresa e Contrato)...")

    cursor.execute("""
                   INSERT INTO empresas (empresa_id, razao_social, cnpj, objeto_contrato, data_contratacao, ativo,
                                         usuario_cadastro)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   """, (mock_uuid, "UROGERCLIN CLÍNICA MÉDICA LTDA", "09.498.547/0001-33", "Serviços de Urologia",
                         data_inicio_teste, 1, "sistema"))

    cursor.execute("""
                   INSERT INTO contratos (empresa_id, servico, quantidade, valor_unitario, data_contratacao,
                                          vigencia_meses, ativo, usuario_cadastro)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   """, (mock_uuid, "Consulta Urologia", 850, 45.00, data_inicio_teste, 24, 1, "sistema"))

    cursor.execute("""
                   INSERT INTO contratos (empresa_id, servico, quantidade, valor_unitario, data_contratacao,
                                          vigencia_meses, ativo, usuario_cadastro)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   """, (mock_uuid, "Avaliação Urodinâmica", 30, 160.00, data_inicio_teste, 24, 1, "sistema"))

    conn.commit()
    conn.close()
    print("Banco de dados 'cadastro.db' recriado com sucesso e populado com dados de teste.")


if __name__ == '__main__':
    setup_environment()