import sqlite3
import os

DB_NAME = 'amb.db'

def setup_db():
    print(f"--- Configurando banco de dados: {DB_NAME} ---")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Tabela de Consultas (producao_amb)
    cursor.execute("""
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
    """)
    
    # 2. Tabela de Exames (producao_exame)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS producao_exame (
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
    """)
    
    try:
        conn.commit()
        print("Tabelas 'producao_amb' e 'producao_exame' verificadas com sucesso.")
    except Exception as e:
        print(f"Erro ao criar tabelas: {e}")
        
    conn.close()

if __name__ == '__main__':
    setup_db()