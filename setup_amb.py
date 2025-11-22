import sqlite3
import os

DB_NAME = 'amb.db'

def setup_db():
    print(f"--- Configurando banco de dados: {DB_NAME} ---")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Criação da tabela producao_amb
    # Estrutura: Especialidade, Oferta, Agendado, Realizado, Mês, Ano, Usuario, Timestamp
    sql_create = """
    CREATE TABLE IF NOT EXISTS producao_amb (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        especialidade TEXT,
        oferta INTEGER,
        agendado INTEGER,
        realizado INTEGER,
        mes TEXT,
        ano INTEGER,
        usuario TEXT,
        timestamp TEXT
    )
    """
    
    try:
        cursor.execute(sql_create)
        print("Tabela 'producao_amb' criada/verificada com sucesso.")
    except Exception as e:
        print(f"Erro ao criar tabela: {e}")
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    setup_db()