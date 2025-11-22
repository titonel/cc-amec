import sqlite3
import pandas as pd
import os

# --- CONFIGURAÇÃO ---
PASTA_MATRIZES = 'matrizes'

# Configuração das exportações: (Banco de Dados, Tabela, Nome do Arquivo de Saída)
EXPORT_CONFIG = [
    {
        'db': 'medicos.db',
        'tabela': 'medicos',
        'arquivo': 'medicos.csv'
    },
    {
        'db': 'medicos.db',
        'tabela': 'especialidades_amec',
        'arquivo': 'especialidades-amec.csv'
    },
    {
        'db': 'producao_cirurgica.db',
        'tabela': 'producao',
        'arquivo': 'producao_cirurgica.csv'
    }
]

def exportar_dados():
    print("--- Iniciando Exportação de Dados ---")
    
    # Garante que a pasta matrizes existe
    if not os.path.exists(PASTA_MATRIZES):
        os.makedirs(PASTA_MATRIZES)
        print(f"Pasta '{PASTA_MATRIZES}' criada.")

    for item in EXPORT_CONFIG:
        db_file = item['db']
        tabela = item['tabela']
        arquivo_saida = os.path.join(PASTA_MATRIZES, item['arquivo'])
        
        if not os.path.exists(db_file):
            print(f"ERRO: Banco de dados '{db_file}' não encontrado. Pulando exportação.")
            continue

        print(f"Lendo tabela '{tabela}' de '{db_file}'...")
        
        try:
            # Conecta ao banco
            conn = sqlite3.connect(db_file)
            
            # Lê os dados para um DataFrame
            query = f"SELECT * FROM {tabela}"
            df = pd.read_sql_query(query, conn)
            
            conn.close()
            
            if df.empty:
                print(f"AVISO: A tabela '{tabela}' está vazia.")
            
            # Exporta para CSV
            # sep=';' para compatibilidade com Excel em PT-BR
            # encoding='utf-8-sig' para garantir que acentos funcionem no Excel
            # index=False para não salvar o índice numérico do Pandas
            df.to_csv(arquivo_saida, sep=';', encoding='utf-8-sig', index=False)
            
            print(f"Sucesso! Dados exportados para '{arquivo_saida}' ({len(df)} registros).")
            
        except Exception as e:
            print(f"Falha ao exportar '{tabela}': {e}")

    print("--- Exportação Concluída ---")

if __name__ == '__main__':
    exportar_dados()