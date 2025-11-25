import sqlite3
import pandas as pd
import os
import re
import unicodedata

# --- CONFIGURAÇÃO ---
DB_FOLDER = 'db'
DB_NAME = os.path.join(DB_FOLDER, 'producao_cirurgica.db')
PASTA_MATRIZES = 'matrizes'

# Garante que a pasta db existe
if not os.path.exists(DB_FOLDER):
    os.makedirs(DB_FOLDER)

# Caminhos
ARQUIVO_PROCEDIMENTOS = os.path.join(PASTA_MATRIZES, 'procedimentos.csv')
ARQUIVO_ESPECIALIDADES = os.path.join(PASTA_MATRIZES, 'especialidades.csv')
ARQUIVO_TIPO_CMA = os.path.join(PASTA_MATRIZES, 'tipo_cma.csv')
ARQUIVO_PRODUCAO = os.path.join(PASTA_MATRIZES, 'producao.csv')

def get_db_conn():
    return sqlite3.connect(DB_NAME)

def inicializar_tabelas():
    """
    Cria a estrutura do banco de dados (DDL) garantindo que as tabelas existam
    mesmo se a importação de CSV falhar.
    """
    conn = get_db_conn()
    cursor = conn.cursor()
    
    print(f"--- Inicializando Estrutura do Banco de Dados: {DB_NAME} ---")

    # 1. Tabela Procedimentos (Padronizado para codigo_sigtap)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS procedimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        codigo_sigtap TEXT UNIQUE,
        valor_sigtap REAL
    )
    """)

    # 2. Tabela Produção (Horizontal - Meses em Colunas)
    # Usa codigo_sigtap para linkar
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS producao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_sigtap TEXT,
        tipo TEXT,
        especialidade TEXT,
        jan REAL DEFAULT 0,
        fev REAL DEFAULT 0,
        mar REAL DEFAULT 0,
        abr REAL DEFAULT 0,
        mai REAL DEFAULT 0,
        jun REAL DEFAULT 0,
        jul REAL DEFAULT 0,
        ago REAL DEFAULT 0,
        "set" REAL DEFAULT 0,
        "out" REAL DEFAULT 0,
        nov REAL DEFAULT 0,
        dez REAL DEFAULT 0
    )
    """)

    # 3. Tabelas Auxiliares (Genéricas)
    # Serão recriadas dinamicamente se o CSV existir, mas criamos um stub aqui
    cursor.execute("CREATE TABLE IF NOT EXISTS especialidades (id TEXT, especialidade TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS tipo_cma (id TEXT, cirurgia TEXT)")

    conn.commit()
    conn.close()
    print("Tabelas criadas/verificadas com sucesso.")

def normalizar_texto(texto):
    """Limpa textos para nomes de colunas."""
    if not isinstance(texto, str): return str(texto)
    nfkd = unicodedata.normalize('NFKD', texto)
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    limpo = sem_acento.lower().strip().replace(' ', '_').replace('/', '_').replace('-', '_')
    return re.sub(r'[^\w]', '', limpo)

def limpar_valor_numerico(valor):
    """Converte '1.200,50' para float."""
    if pd.isna(valor) or valor == '': return 0.0
    valor = str(valor)
    limpo = re.sub(r'[^\d.,-]', '', valor)
    if ',' in limpo:
        limpo = limpo.replace('.', '').replace(',', '.')
    try:
        return float(limpo)
    except ValueError:
        return 0.0

def carregar_csv(caminho):
    if not os.path.exists(caminho):
        print(f"AVISO: Arquivo não encontrado: {caminho}")
        return pd.DataFrame()
    
    try:
        # Tenta ; primeiro
        df = pd.read_csv(caminho, sep=';', encoding='latin-1', dtype=str)
        if len(df.columns) > 1: return df
        # Tenta ,
        df = pd.read_csv(caminho, sep=',', encoding='latin-1', dtype=str)
        return df
    except Exception as e:
        print(f"Erro ao ler {caminho}: {e}")
        return pd.DataFrame()

def importar_procedimentos():
    print("Importando Procedimentos...")
    df = carregar_csv(ARQUIVO_PROCEDIMENTOS)
    if df.empty: return

    # Normaliza colunas do CSV
    df.columns = [normalizar_texto(c) for c in df.columns]
    
    # Mapeia para nomes do banco
    mapa = {}
    for c in df.columns:
        if 'sus' in c or 'codigo' in c or 'cod' in c: mapa[c] = 'codigo_sigtap'
        elif 'nome' in c or 'procedimento' in c or 'descricao' in c: mapa[c] = 'nome'
        elif 'valor' in c or 'sigtap' in c: mapa[c] = 'valor_sigtap'
    
    df = df.rename(columns=mapa)
    
    # Garante colunas necessárias
    if 'codigo_sigtap' not in df.columns: return

    if 'valor_sigtap' in df.columns:
        df['valor_sigtap'] = df['valor_sigtap'].apply(limpar_valor_numerico)

    # Seleciona apenas colunas que existem no banco para evitar erro
    cols_banco = ['nome', 'codigo_sigtap', 'valor_sigtap']
    cols_existentes = [c for c in cols_banco if c in df.columns]
    df = df[cols_existentes]

    conn = get_db_conn()
    # Append ou Replace? Replace limpa tudo e insere o novo
    df.to_sql('procedimentos', conn, if_exists='replace', index=False)
    conn.close()
    print(f"Procedimentos importados: {len(df)}")

def importar_producao():
    print("Importando Produção...")
    df = carregar_csv(ARQUIVO_PRODUCAO)
    if df.empty: return

    # Mapeamento
    cols_orig = list(df.columns)
    cols_norm = [normalizar_texto(c) for c in cols_orig]
    mapa_orig = dict(zip(cols_norm, cols_orig))

    df_final = pd.DataFrame()
    
    # Identifica Chaves
    col_cod = next((c for c in cols_norm if 'codigo' in c or 'sigtap' in c), None)
    col_tipo = next((c for c in cols_norm if 'tipo' in c), None)
    col_esp = next((c for c in cols_norm if 'especialidade' in c), None)

    if not col_cod:
        print("ERRO: Coluna de código não encontrada na produção.")
        return

    df_final['codigo_sigtap'] = df[mapa_orig[col_cod]]
    if col_tipo: df_final['tipo'] = df[mapa_orig[col_tipo]]
    if col_esp: df_final['especialidade'] = df[mapa_orig[col_esp]]

    # Meses
    meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
    for m in meses:
        if m in mapa_orig:
            df_final[m] = df[mapa_orig[m]].apply(limpar_valor_numerico)
        else:
            df_final[m] = 0.0

    conn = get_db_conn()
    # Drop para garantir schema limpo
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS producao") 
    # Recria schema correto (para garantir tipos REAL e nomes com aspas)
    cursor.execute("""
    CREATE TABLE producao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_sigtap TEXT,
        tipo TEXT,
        especialidade TEXT,
        jan REAL, fev REAL, mar REAL, abr REAL, mai REAL, jun REAL,
        jul REAL, ago REAL, "set" REAL, "out" REAL, nov REAL, dez REAL
    )
    """)
    df_final.to_sql('producao', conn, if_exists='append', index=False)
    conn.close()
    print(f"Produção importada: {len(df_final)}")

def importar_auxiliar(nome, arquivo):
    print(f"Importando {nome}...")
    df = carregar_csv(arquivo)
    if df.empty: return
    
    df.columns = [normalizar_texto(c) for c in df.columns]
    conn = get_db_conn()
    df.to_sql(nome, conn, if_exists='replace', index=False)
    conn.close()
    print(f"{nome} importada: {len(df)}")

def main():
    # 1. Cria tabelas vazias (evita erro no app)
    inicializar_tabelas()
    
    # 2. Tenta importar dados (se arquivos existirem)
    if not os.path.exists(PASTA_MATRIZES):
        os.makedirs(PASTA_MATRIZES)
        print(f"AVISO: Pasta '{PASTA_MATRIZES}' criada. Coloque os arquivos CSV lá.")
    
    importar_procedimentos()
    importar_producao()
    importar_auxiliar('especialidades', ARQUIVO_ESPECIALIDADES)
    importar_auxiliar('tipo_cma', ARQUIVO_TIPO_CMA)
    
    print("\n--- Setup Concluído ---")

if __name__ == '__main__':
    main()