import sqlite3
import pandas as pd
import re
import os

# --- CONFIGURAÇÃO ---
DB_NAME = 'producao_cirurgica.db'
# Caminho relativo para o arquivo na pasta matrizes
CAMINHO_ARQUIVO = os.path.join('matrizes', 'Planilha Roxa Unica.csv')

def criar_tabelas(cursor):
    """Cria as tabelas necessárias no banco de dados."""
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS procedimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        codigo_sus TEXT NOT NULL UNIQUE,
        valor_sigtap REAL
    )
    ''')
    
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
    print("Tabelas verificadas com sucesso.")

def limpar_valor(valor):
    """Converte valor para float. Retorna 0.0 se falhar ou for nulo/'0'."""
    # Verifica se é nulo, vazio ou zero literal (string ou número)
    if pd.isna(valor) or valor == '' or valor == '0' or valor == 0:
        return 0.0
    
    valor_str = str(valor)
    # Remove qualquer coisa que não seja número, ponto ou vírgula
    limpo = re.sub(r'[^\d.,]', '', valor_str)
    
    # Tratamento para formato brasileiro (1.000,00 -> 1000.00)
    # Se tiver vírgula, assume que é decimal
    if ',' in limpo:
        limpo = limpo.replace('.', '').replace(',', '.')
    
    try:
        return float(limpo)
    except (ValueError, TypeError):
        return 0.0

def importar_arquivo_unico(cursor):
    if not os.path.exists(CAMINHO_ARQUIVO):
        print(f"ERRO CRÍTICO: Arquivo não encontrado: {CAMINHO_ARQUIVO}")
        print("Verifique se a pasta 'matrizes' existe e se o arquivo está dentro dela.")
        return 0

    print(f"Lendo arquivo: {CAMINHO_ARQUIVO}...")

    try:
        # Lê o CSV:
        # - sep=';': Separador padrão
        # - header=0: A primeira linha (índice 0) contém os títulos
        # - usecols=range(17): Importa apenas as colunas 0 a 16 (as 17 primeiras)
        # - dtype=str: Lê tudo como texto para evitar erros de tipo antes do tratamento
        # - encoding='latin-1': Para aceitar acentos corretamente
        df = pd.read_csv(
            CAMINHO_ARQUIVO, 
            sep=';', 
            header=0, 
            usecols=range(17), 
            dtype=str, 
            encoding='latin-1',
            on_bad_lines='skip'
        )
    except Exception as e:
        print(f"Erro ao ler o arquivo CSV: {e}")
        return 0

    # REQUISITO: Sempre que não for localizado algum registro, lançar como 0
    # Preenche todos os NaNs/Vazios com a string '0'
    df = df.fillna('0')

    # Validação básica de colunas
    if len(df.columns) < 3:
        print("Erro: O arquivo não possui as colunas mínimas (Nome, Código, Valor).")
        return 0

    # Renomeação forçada das 3 primeiras colunas pela posição
    # Isso evita erros caso o cabeçalho tenha caracteres estranhos
    colunas = list(df.columns)
    colunas[0] = 'nome'
    colunas[1] = 'codigo_sus'
    colunas[2] = 'valor_sigtap'
    df.columns = colunas

    contador = 0

    # Itera sobre as linhas do DataFrame
    for _, row in df.iterrows():
        raw_nome = str(row['nome'])
        raw_codigo = str(row['codigo_sus'])
        raw_valor = str(row['valor_sigtap'])

        # Se a linha for inteiramente '0' (ou cabeçalho perdido), ignoramos
        if raw_codigo == '0' and raw_nome == '0':
            continue
        
        # Lógica de "Normalização" 
        # Mantém a lógica de separar por '/' caso existam células agrupadas
        nomes = raw_nome.split(' / ')
        codigos = raw_codigo.replace(' ', '').split('/')
        valores = raw_valor.split('/')
        
        # Limpa os valores monetários
        valores_limpos = [limpar_valor(v) for v in valores]

        # Cenário 1: Listas com mesmo tamanho (ex: 2 nomes, 2 códigos, 2 valores)
        if len(nomes) > 1 and len(nomes) == len(codigos):
            # Se faltar valor na lista (ex: 2 nomes mas só 1 valor), ajusta
            if len(valores_limpos) != len(nomes):
                valor_padrao = valores_limpos[0] if valores_limpos else 0.0
                valores_limpos = [valor_padrao] * len(nomes)

            for n, c, v in zip(nomes, codigos, valores_limpos):
                inserir_registro(cursor, n, c, v)
                contador += 1
        
        # Cenário 2: Registro Único (o mais comum) ou agrupamentos simples
        elif len(nomes) >= 1:
            n = nomes[0].strip()
            # Pega o primeiro código ou '0' se lista vazia
            c = codigos[0].strip() if codigos else '0'
            v = valores_limpos[0] if valores_limpos else 0.0

            # Só insere se o código for diferente de '0' e tiver tamanho mínimo razoável
            # Se quiser importar TUDO, mesmo lixo, remova a verificação len(c) > 5
            if c != '0' and len(c) > 5:
                inserir_registro(cursor, n, c, v)
                contador += 1

    return contador

def inserir_registro(cursor, nome, codigo, valor):
    """Tenta inserir no banco, ignorando duplicatas de código SUS."""
    nome = nome.strip()
    codigo = codigo.strip()
    
    # Verifica novamente se não é dado inválido
    if not nome or nome == '0' or not codigo or codigo == '0': 
        return

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO procedimentos (nome, codigo_sus, valor_sigtap) VALUES (?, ?, ?)",
            (nome, codigo, valor)
        )
    except sqlite3.Error as e:
        print(f"Erro SQL ao inserir {nome}: {e}")

def main():
    # Remove banco antigo para garantir atualização limpa e evitar duplicatas antigas
    if os.path.exists(DB_NAME):
        try:
            os.remove(DB_NAME)
            print(f"Banco de dados anterior '{DB_NAME}' removido.")
        except PermissionError:
            print("ERRO: O banco de dados está aberto em outro programa. Feche e tente novamente.")
            return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    criar_tabelas(cursor)
    
    total_inseridos = importar_arquivo_unico(cursor)
    
    conn.commit()
    conn.close()
    
    print("\n--- Concluído ---")
    print(f"Total de procedimentos importados: {total_inseridos}")
    print("Agora você pode executar o 'app.py'.")

if __name__ == '__main__':
    main()