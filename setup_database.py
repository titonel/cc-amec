import sqlite3
import pandas as pd
import re
import os

# --- CONFIGURAÇÃO ---
DB_NAME = 'producao_cirurgica.db'
# Mapeia os nomes dos arquivos para o 'tipo' no banco de dados
ARQUIVOS_CSV = {
    'matrizes\Planilha Roxa de Procedimentos Cirúrgicos.xlsx - CMA_-_CC.csv': '1-Maior',
    'matrizes\Planilha Roxa de Procedimentos Cirúrgicos.xlsx - cma_-_SPC.csv': '2-Menor'
}
# --- FIM DA CONFIGURAÇÃO ---

def criar_tabelas(cursor):
    """Cria as tabelas no banco de dados se não existirem."""
    # Tabela para os procedimentos (master data)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS procedimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        codigo_sus TEXT NOT NULL UNIQUE,
        valor_sigtap REAL,
        tipo_origem TEXT
    )
    ''')
    # Tabela para a produção (registros mensais)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS producao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        procedimento_id INTEGER NOT NULL,
        ano INTEGER NOT NULL,
        mes INTEGER NOT NULL,
        quantidade INTEGER NOT NULL,
        FOREIGN KEY(procedimento_id) REFERENCES procedimentos(id)
    )
    ''')
    print("Tabelas 'procedimentos' e 'producao' criadas com sucesso.")

def limpar_valor(valor_str):
    """Limpa e converte a string de valor para um float."""
    if not isinstance(valor_str, str):
        return None
    # Remove espaços, " e troca vírgula por ponto
    valor_limpo = valor_str.replace('"', '').replace(' ', '').replace('.', '').replace(',', '.')
    try:
        return float(valor_limpo)
    except (ValueError, TypeError):
        return None

def processar_arquivo(filepath, tipo_origem, cursor):
    """Lê, limpa, normaliza e insere os dados do CSV no banco."""
    if not os.path.exists(filepath):
        print(f"AVISO: Arquivo não encontrado: {filepath}. Pulando.")
        return 0
        
    print(f"Processando arquivo: {filepath}...")
    # Tenta ler o CSV com codificação latin-1, separador ';' e cabeçalho na linha 4 (índice 3)
    try:
        df = pd.read_csv(filepath, sep=';', header=3, encoding='latin-1', on_bad_lines='skip', dtype=str)
    except Exception as e:
        print(f"Erro ao ler o CSV {filepath}: {e}")
        return 0

    # 1. Verifica se existem colunas suficientes (para evitar erro de índice)
    if len(df.columns) < 3:
        print(f"  Erro: O arquivo {filepath} tem menos de 3 colunas.")
        return 0
    
    # 2. Pega a lista atual de nomes de colunas
    colunas_atuais = list(df.columns)

    # 3. Sobrescreve manualmente os nomes das 3 primeiras posições
    colunas_atuais[0] = 'nome'
    colunas_atuais[1] = 'codigo_sus'
    colunas_atuais[2] = 'valor_sigtap'

    # 4. Devolve a lista modificada para o DataFrame
    # Isso ignora completamente o que estava escrito lá antes, evitando o erro de Hash
    df.columns = colunas_atuais    

    # Filtra apenas linhas que parecem ter um código SUS válido (xx.xx.xx.xxx-x)
    # Isso ajuda a remover linhas de cabeçalho extras, totais ou em branco
    df_filtrado = df[
        df['codigo_sus'].astype(str).str.match(r'\d{2}\.\d{2}\.\d{2}\.\d{3}-\d', na=False) |
        df['codigo_sus'].astype(str).str.contains(r'/', na=False)
    ].copy()

    contador_inseridos = 0
    for _, row in df_filtrado.iterrows():
        # Pega os valores da linha
        nomes = str(row['nome']).split(' / ')
        codigos = str(row['codigo_sus']).replace(' ', '').split('/')
        valores = str(row['valor_sigtap']).split('/')

        # Limpa os valores monetários
        valores_limpos = [limpar_valor(v) for v in valores]

        # Verifica se os dados estão consistentes para normalização
        if len(nomes) > 1 and len(nomes) == len(codigos) == len(valores_limpos):
            # Caso 1: Múltiplos procedimentos na mesma linha (ex: Herniorrafia)
            # Vamos separar em múltiplas entradas
            for nome, codigo, valor in zip(nomes, codigos, valores_limpos):
                if nome and codigo:
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO procedimentos (nome, codigo_sus, valor_sigtap, tipo_origem) VALUES (?, ?, ?, ?)",
                            (nome.strip(), codigo.strip(), valor, tipo_origem)
                        )
                        contador_inseridos += 1
                    except sqlite3.Error as e:
                        print(f"Erro ao inserir {nome} ({codigo}): {e}")
        elif len(nomes) == 1 and len(codigos) == 1 and len(valores_limpos) >= 1:
            # Caso 2: Procedimento único na linha
            nome = nomes[0].strip()
            codigo = codigos[0].strip()
            valor = valores_limpos[0]
            if nome and codigo and re.match(r'\d{2}\.\d{2}\.\d{2}\.\d{3}-\d', codigo):
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO procedimentos (nome, codigo_sus, valor_sigtap, tipo_origem) VALUES (?, ?, ?, ?)",
                        (nome, codigo, valor, tipo_origem)
                    )
                    contador_inseridos += 1
                except sqlite3.Error as e:
                    print(f"Erro ao inserir {nome} ({codigo}): {e}")
        else:
            # Caso 3: Dados inconsistentes, pular linha
            print(f"Pulando linha inconsistente: {row['nome']} | {row['codigo_sus']}")

    return contador_inseridos

def main():
    # Deleta o banco de dados antigo para recomeçar
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"Banco de dados '{DB_NAME}' antigo removido.")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    criar_tabelas(cursor)
    
    total_registros = 0
    for filepath, tipo in ARQUIVOS_CSV.items():
        registros = processar_arquivo(filepath, tipo, cursor)
        total_registros += registros
        print(f"Inseridos {registros} procedimentos de {filepath}")

    conn.commit()
    conn.close()
    
    print("\n--- Processamento Concluído ---")
    print(f"Total de {total_registros} procedimentos únicos inseridos no banco '{DB_NAME}'.")
    print("Você já pode executar o 'app.py' para iniciar o servidor web.")

if __name__ == '__main__':
    main()