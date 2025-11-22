import sqlite3
import pandas as pd
import os
import re
import unicodedata

# --- CONFIGURAÇÃO ---
DB_NAME = 'medicos.db'
ARQUIVO_CSV = os.path.join('matrizes', 'medicos.csv')
ARQUIVO_ESPECIALIDADES_AMEC = os.path.join('matrizes', 'especialidades-amec.csv')

# Colunas definidas na especificação
COLUNAS_ESPERADAS = [
    'nome', 'crm', 'dn', 'especialidade', 'nacionalidade', 'naturalidade', 'estado_natural',
    'tel_ddd', 'tel_cel', 'email', 'cpf', 'rg', 'cep_res', 'end_res', 
    'num_res', 'comp_res', 'bairro_res', 'cidade_res', 'estado_res',
    'ativo', 'inicio_ativ', 'fim_ativ', 'sexo'
]

def get_db_conn():
    return sqlite3.connect(DB_NAME)

def normalizar_texto(texto):
    """Remove acentos e caracteres especiais para nomes de colunas."""
    if not isinstance(texto, str): return str(texto)
    nfkd = unicodedata.normalize('NFKD', texto)
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r'[^\w]', '', sem_acento.lower().strip().replace(' ', '_'))

def carregar_csv_robusto(caminho):
    """Tenta ler CSV com diferentes codificações e separadores."""
    if not os.path.exists(caminho):
        print(f"ERRO: Arquivo não encontrado: {caminho}")
        return pd.DataFrame()
    
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
    separadores = [';', ',']
    
    for encoding in encodings:
        for sep in separadores:
            try:
                df = pd.read_csv(caminho, sep=sep, encoding=encoding, dtype=str)
                if len(df.columns) >= 1:
                    return df
            except: continue
            
    return pd.DataFrame()

def importar_especialidades_amec():
    print("Importando Especialidades AMEC...")
    df = carregar_csv_robusto(ARQUIVO_ESPECIALIDADES_AMEC)
    
    if df.empty:
        print("AVISO: Arquivo de especialidades vazio ou não encontrado.")
        # Cria tabela vazia para não quebrar o app
        conn = get_db_conn()
        conn.execute("CREATE TABLE IF NOT EXISTS especialidades_amec (id INTEGER PRIMARY KEY, especialidade TEXT)")
        conn.close()
        return

    # Normaliza colunas
    df.columns = [normalizar_texto(c) for c in df.columns]
    
    # Procura a coluna de nome (especialidade, nome, descricao...)
    col_nome = next((c for c in df.columns if 'especialidade' in c or 'nome' in c or 'descricao' in c), None)
    
    if not col_nome:
        # Se só tem 1 coluna, assume que é ela
        if len(df.columns) == 1:
            col_nome = df.columns[0]
        else:
            print("ERRO: Não foi possível identificar a coluna de nome da especialidade.")
            return

    # Prepara DataFrame final
    df_final = pd.DataFrame()
    df_final['especialidade'] = df[col_nome].str.upper().str.strip() # Padroniza em maiúsculo
    df_final = df_final.drop_duplicates().sort_values('especialidade')

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS especialidades_amec")
    cursor.execute("CREATE TABLE especialidades_amec (id INTEGER PRIMARY KEY AUTOINCREMENT, especialidade TEXT)")
    
    try:
        df_final.to_sql('especialidades_amec', conn, if_exists='append', index=False)
        print(f"Sucesso! {len(df_final)} especialidades importadas.")
    except Exception as e:
        print(f"Erro ao importar especialidades: {e}")
        
    conn.commit()
    conn.close()

def configurar_banco_medicos():
    print(f"--- Configurando banco de dados: {DB_NAME} ---")
    
    df = carregar_csv_robusto(ARQUIVO_CSV)
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS_ESPERADAS)

    # 1. Normalização de Colunas
    print("Mapeando colunas de médicos...")
    novo_mapa = {}
    
    for col in df.columns:
        col_norm = normalizar_texto(col)
        match = None
        # ... (Lógica de mapeamento mantida igual) ...
        if 'nome' in col_norm: match = 'nome'
        elif 'crm' in col_norm: match = 'crm'
        elif 'nasc' in col_norm or col_norm == 'dn': match = 'dn'
        elif 'especialidade' in col_norm: match = 'especialidade'
        elif 'nacionalidade' in col_norm or 'pais' in col_norm: match = 'nacionalidade'
        elif 'naturalidade' in col_norm and 'estado' not in col_norm: match = 'naturalidade'
        elif 'estado_natural' in col_norm or ('uf' in col_norm and 'nasc' in col_norm): match = 'estado_natural'
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
        elif 'sexo' in col_norm: match = 'sexo'
        
        if match: novo_mapa[col] = match
    
    if novo_mapa: df = df.rename(columns=novo_mapa)
    
    # 2. Default Values
    defaults = {'ativo': '1', 'sexo': '0', 'inicio_ativ': '', 'fim_ativ': '', 'estado_natural': ''}
    for c, v in defaults.items():
        if c not in df.columns: df[c] = v

    for col in COLUNAS_ESPERADAS:
        if col not in df.columns: df[col] = ''
            
    df = df[COLUNAS_ESPERADAS]
    df = df.fillna('')
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

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
    # Importa a tabela auxiliar de especialidades
    importar_especialidades_amec()
    # Importa os médicos
    configurar_banco_medicos()