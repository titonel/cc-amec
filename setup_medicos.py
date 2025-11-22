import sqlite3
import pandas as pd
import os
import re
import unicodedata

# --- CONFIGURAÇÃO ---
DB_NAME = 'medicos.db'
ARQUIVO_CSV = os.path.join('matrizes', 'medicos.csv')

# Colunas definidas na especificação (Incluindo novos campos)
COLUNAS_ESPERADAS = [
    'nome', 'crm', 'dn', 'especialidade', 'nacionalidade', 'naturalidade', 
    'tel_ddd', 'tel_cel', 'email', 'cpf', 'rg', 'cep_res', 'end_res', 
    'num_res', 'comp_res', 'bairro_res', 'cidade_res', 'estado_res',
    'ativo', 'inicio_ativ', 'fim_ativ', 'sexo'  # Novo campo sexo
]

def get_db_conn():
    return sqlite3.connect(DB_NAME)

def normalizar_texto(texto):
    """Remove acentos e caracteres especiais para nomes de colunas."""
    if not isinstance(texto, str): return str(texto)
    nfkd = unicodedata.normalize('NFKD', texto)
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r'[^\w]', '', sem_acento.lower().strip().replace(' ', '_'))

def carregar_csv_medicos():
    if not os.path.exists(ARQUIVO_CSV):
        print(f"ERRO: Arquivo não encontrado: {ARQUIVO_CSV}")
        print("Certifique-se de que a pasta 'matrizes' existe e o arquivo 'medicos.csv' está dentro dela.")
        return pd.DataFrame()
    
    try:
        # Tenta ler com separador ; (padrão comum)
        df = pd.read_csv(ARQUIVO_CSV, sep=';', encoding='latin-1', dtype=str)
        
        # Se falhar (ex: só 1 coluna), tenta vírgula
        if len(df.columns) <= 1:
            df = pd.read_csv(ARQUIVO_CSV, sep=',', encoding='latin-1', dtype=str)
            
        print(f"Arquivo lido com sucesso. Registros encontrados: {len(df)}")
        return df
    except Exception as e:
        print(f"Erro ao ler CSV: {e}")
        return pd.DataFrame()

def configurar_banco():
    print(f"--- Configurando banco de dados: {DB_NAME} ---")
    
    df = carregar_csv_medicos()
    if df.empty:
        # Cria DataFrame vazio com colunas se não houver CSV
        df = pd.DataFrame(columns=COLUNAS_ESPERADAS)

    # 1. Normalização de Colunas
    colunas_atuais = list(df.columns)
    
    print("Tentando identificar colunas pelo nome...")
    novo_mapa = {}
    
    for col in df.columns:
        col_norm = normalizar_texto(col)
        
        match = None
        if 'nome' in col_norm: match = 'nome'
        elif 'crm' in col_norm: match = 'crm'
        elif 'nasc' in col_norm or col_norm == 'dn': match = 'dn'
        elif 'especialidade' in col_norm: match = 'especialidade'
        elif 'nacionalidade' in col_norm: match = 'nacionalidade'
        elif 'naturalidade' in col_norm: match = 'naturalidade'
        elif 'ddd' in col_norm: match = 'tel_ddd'
        elif 'cel' in col_norm: match = 'tel_cel'
        elif 'email' in col_norm: match = 'email'
        elif 'cpf' in col_norm: match = 'cpf'
        elif 'rg' in col_norm: match = 'rg'
        elif 'cep' in col_norm: match = 'cep_res'
        elif 'endereco' in col_norm or 'end' in col_norm: match = 'end_res'
        elif 'num' in col_norm: match = 'num_res'
        elif 'comp' in col_norm: match = 'comp_res'
        elif 'bairro' in col_norm: match = 'bairro_res'
        elif 'cidade' in col_norm: match = 'cidade_res'
        elif 'estado' in col_norm or 'uf' in col_norm: match = 'estado_res'
        elif 'inicio' in col_norm: match = 'inicio_ativ'
        elif 'fim' in col_norm: match = 'fim_ativ'
        elif 'ativo' in col_norm: match = 'ativo'
        elif 'sexo' in col_norm or 'genero' in col_norm: match = 'sexo'
        
        if match:
            novo_mapa[col] = match
    
    if novo_mapa:
        df = df.rename(columns=novo_mapa)
    
    # 2. Adicionar colunas faltantes com valores padrão
    if 'ativo' not in df.columns:
        df['ativo'] = '1'
    if 'sexo' not in df.columns:
        df['sexo'] = '0' # Default Masculino se não especificado
    if 'inicio_ativ' not in df.columns:
        df['inicio_ativ'] = ''
    if 'fim_ativ' not in df.columns:
        df['fim_ativ'] = ''

    # Garante estrutura final
    for col in COLUNAS_ESPERADAS:
        if col not in df.columns:
            df[col] = ''
            
    df = df[COLUNAS_ESPERADAS]

    # 3. Limpeza
    df = df.fillna('')
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    # 4. Recria Tabela
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS medicos")
    
    cols_sql = ", ".join([f"{c} TEXT" for c in COLUNAS_ESPERADAS])
    sql_create = f"CREATE TABLE medicos (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})"
    cursor.execute(sql_create)
    
    try:
        df.to_sql('medicos', conn, if_exists='append', index=False)
        print(f"Sucesso! {len(df)} médicos importados.")
    except Exception as e:
        print(f"Erro SQL: {e}")

    conn.commit()
    conn.close()

if __name__ == '__main__':
    configurar_banco()