import sqlite3
import os
from datetime import datetime

# Configuração de Caminhos
DB_FOLDER = 'db'
DB_AMB = os.path.join(DB_FOLDER, 'amb.db')


def setup_ambulatorial():
    print(f"--- Configurando Banco Ambulatorial: {DB_AMB} ---")

    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    conn = sqlite3.connect(DB_AMB)
    cursor = conn.cursor()

    # 1. Criar Tabela de Consultas (producao_amb)
    print("Criando/Verificando tabela 'producao_amb'...")
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS producao_amb
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       especialidade
                       TEXT,
                       oferta
                       INTEGER,
                       agendado
                       INTEGER,
                       realizado
                       INTEGER,
                       mes
                       TEXT,
                       ano
                       INTEGER,
                       usuario
                       TEXT,
                       timestamp
                       TEXT
                   )
                   """)

    # 2. Criar Tabela de Exames (producao_exame)
    print("Criando/Verificando tabela 'producao_exame'...")
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS producao_exame
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       especialidade
                       TEXT,
                       oferta
                       INTEGER,
                       agendado
                       INTEGER,
                       realizado
                       INTEGER,
                       mes
                       TEXT,
                       ano
                       INTEGER,
                       usuario
                       TEXT,
                       timestamp
                       TEXT
                   )
                   """)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 3. Inserir Dados de Teste em CONSULTAS
    cursor.execute("SELECT count(*) FROM producao_amb")
    count_amb = cursor.fetchone()[0]

    if count_amb == 0:
        print("Inserindo dados de teste em 'producao_amb'...")
        dados_teste_amb = [
            ("Cardiologia", 100, 95, 80, "Janeiro", 2025, "sistema", ts),
            ("Cardiologia", 100, 90, 85, "Fevereiro", 2025, "sistema", ts),
            ("Dermatologia", 80, 80, 75, "Janeiro", 2025, "sistema", ts),
            ("Ortopedia", 150, 140, 110, "Janeiro", 2025, "sistema", ts),
            ("Urologia", 60, 55, 50, "Janeiro", 2025, "sistema", ts),
            ("Oftalmologia", 200, 190, 180, "Janeiro", 2025, "sistema", ts)
        ]
        cursor.executemany("""
                           INSERT INTO producao_amb (especialidade, oferta, agendado, realizado, mes, ano, usuario,
                                                     timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           """, dados_teste_amb)
        print(f"{len(dados_teste_amb)} registros de CONSULTAS inseridos.")
    else:
        print(f"Tabela 'producao_amb' já contém {count_amb} registros.")

    # 4. Inserir Dados de Teste em EXAMES (NOVO BLOCO DE INSERÇÃO)
    cursor.execute("SELECT count(*) FROM producao_exame")
    count_exame = cursor.fetchone()[0]

    if count_exame == 0:
        print("Inserindo dados de teste em 'producao_exame'...")
        dados_teste_exame = [
            ("Ressonância Magnética", 50, 48, 45, "Janeiro", 2025, "sistema", ts),
            ("Tomografia", 100, 100, 92, "Janeiro", 2025, "sistema", ts),
            ("Ultrassonografia", 200, 180, 150, "Janeiro", 2025, "sistema", ts),
            ("Endoscopia", 60, 60, 58, "Janeiro", 2025, "sistema", ts),
            ("Ecocardiograma", 80, 75, 70, "Janeiro", 2025, "sistema", ts)
        ]
        cursor.executemany("""
                           INSERT INTO producao_exame (especialidade, oferta, agendado, realizado, mes, ano, usuario,
                                                       timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           """, dados_teste_exame)
        print(f"{len(dados_teste_exame)} registros de EXAMES inseridos.")
    else:
        print(f"Tabela 'producao_exame' já contém {count_exame} registros.")

    conn.commit()
    conn.close()
    print("Configuração do banco ambulatorial concluída com sucesso.")


if __name__ == '__main__':
    setup_ambulatorial()