import sqlite3
import pandas as pd
import os

# --- CONFIGURAÇÃO ---
PASTA_MATRIZES = 'matrizes'
DB_FOLDER = 'db'

# Garante que a pasta de exportação existe
if not os.path.exists(PASTA_MATRIZES):
    os.makedirs(PASTA_MATRIZES)
    print(f"Pasta '{PASTA_MATRIZES}' criada.")

# Configuração das exportações: (Banco de Dados, Tabela, Nome do Arquivo de Saída)
# Agora inclui todas as bases de dados e tabelas relevantes do sistema
EXPORT_CONFIG = [
    # --- MEDICOS.DB ---
    {
        'db': os.path.join(DB_FOLDER, 'medicos.db'),
        'tabela': 'medicos',
        'arquivo': 'medicos.csv'
    },
    {
        'db': os.path.join(DB_FOLDER, 'medicos.db'),
        'tabela': 'especialidades_amec',
        'arquivo': 'especialidades-amec.csv'
    },

    # --- PRODUCAO_CIRURGICA.DB ---
    {
        'db': os.path.join(DB_FOLDER, 'producao_cirurgica.db'),
        'tabela': 'producao',
        'arquivo': 'producao_cirurgica.csv'
    },

    # --- AMB.DB (Produção Ambulatorial) ---
    {
        'db': os.path.join(DB_FOLDER, 'amb.db'),
        'tabela': 'producao_amb',
        'arquivo': 'producao_ambulatorial.csv'
    },
    {
        'db': os.path.join(DB_FOLDER, 'amb.db'),
        'tabela': 'producao_exame',  # Adicionando caso exista, se não existir o script lida com o erro gracefully
        'arquivo': 'producao_exames.csv'
    },

    # --- CADASTRO.DB (Usuários e Empresas) ---
    {
        'db': os.path.join(DB_FOLDER, 'cadastro.db'),
        'tabela': 'usuarios',
        'arquivo': 'usuarios_sistema.csv'
    },
    {
        'db': os.path.join(DB_FOLDER, 'cadastro.db'),
        'tabela': 'empresas',
        'arquivo': 'empresas_cadastradas.csv'
    },
    {
        'db': os.path.join(DB_FOLDER, 'cadastro.db'),
        'tabela': 'contratos',
        'arquivo': 'contratos_empresas.csv'
    }
]


def exportar_dados():
    print("--- Iniciando Exportação de Dados ---")
    print(f"Lendo bancos de dados da pasta: {DB_FOLDER}")
    print(f"Salvando arquivos CSV em: {PASTA_MATRIZES}")
    print("-" * 40)

    sucessos = 0
    falhas = 0

    for item in EXPORT_CONFIG:
        db_file = item['db']
        tabela = item['tabela']
        arquivo_saida = os.path.join(PASTA_MATRIZES, item['arquivo'])

        # Verifica se o arquivo do banco existe
        if not os.path.exists(db_file):
            print(f"[PULADO] Banco de dados não encontrado: '{db_file}' (Tabela: {tabela})")
            continue

        try:
            # Conecta ao banco
            conn = sqlite3.connect(db_file)

            # Verifica se a tabela existe antes de tentar ler
            cursor = conn.cursor()
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tabela}';")
            if not cursor.fetchone():
                print(f"[PULADO] Tabela '{tabela}' não existe no banco '{os.path.basename(db_file)}'.")
                conn.close()
                continue

            # Lê os dados para um DataFrame
            query = f"SELECT * FROM {tabela}"
            df = pd.read_sql_query(query, conn)
            conn.close()

            if df.empty:
                print(f"[AVISO] A tabela '{tabela}' está vazia. Arquivo CSV será criado apenas com cabeçalho.")

            # Exporta para CSV
            # sep=';' para compatibilidade com Excel em PT-BR
            # encoding='utf-8-sig' para garantir que acentos funcionem no Excel
            # index=False para não salvar o índice numérico do Pandas
            df.to_csv(arquivo_saida, sep=';', encoding='utf-8-sig', index=False)

            print(f"[SUCESSO] {tabela.upper()} -> {item['arquivo']} ({len(df)} registros)")
            sucessos += 1

        except Exception as e:
            print(f"[ERRO] Falha ao exportar '{tabela}': {e}")
            falhas += 1

    print("-" * 40)
    print(f"Exportação Concluída. Sucessos: {sucessos} | Falhas/Pulados: {falhas}")


if __name__ == '__main__':
    exportar_dados()