import time
import os
import glob
import pandas as pd
import pytesseract
from PIL import Image
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURAÇÕES ---
URL_SIRESP_LOGIN = "https://www.siresp.saude.sp.gov.br/"
URL_RELATORIO = "https://ambulatorial.siresp.saude.sp.gov.br/report_rel_consulta.php?P=report_rel_consulta"
USER = "stbastos"
PASS = "Catarina@2016"
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

# Mapeamento de respostas para a 2ª validação
RESPOSTAS_VALIDACAO = {
    '3 últimos dígitos do RG': '994',
    '3 últimos dígitos do CPF': '710',
    '3 primeiros dígitos do RG': '620',
    '3 primeiros dígitos do CPF': '083'
}

def configurar_navegador():
    """Configura o Chrome com preferências de download."""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    # Limpa downloads anteriores para evitar confusão
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        try: os.remove(f)
        except: pass

    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # options.add_argument("--headless") # Descomente para rodar em background

    # Configurações de Download
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)

    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def carregar_dataframe(filepath, callback_log):
    """
    Tenta carregar o arquivo baixado em um DataFrame Pandas.
    Lida com a peculiaridade de sistemas antigos exportarem HTML como .xls.
    """
    try:
        # Tentativa 1: Excel Padrão (.xlsx ou .xls real)
        return pd.read_excel(filepath)
    except Exception as e_excel:
        callback_log(f"Aviso: Falha ao ler como Excel nativo ({str(e_excel)}). Tentando HTML...")
        try:
            # Tentativa 2: Tabela HTML salva como .xls (Comum em PHP legado)
            # Requer lxml ou html5lib instalados
            tabelas = pd.read_html(filepath, decimal=',', thousands='.')
            if tabelas:
                return tabelas[0]
            else:
                raise Exception("Nenhuma tabela encontrada no HTML.")
        except Exception as e_html:
            callback_log(f"Aviso: Falha ao ler como HTML ({str(e_html)}). Tentando CSV...")
            try:
                # Tentativa 3: CSV mascarado
                return pd.read_csv(filepath, sep=';', encoding='latin1')
            except Exception as e_csv:
                raise Exception(f"Não foi possível ler o arquivo. Formatos Excel, HTML e CSV falharam.")

def run_siresp_extraction(callback_log):
    driver = None
    try:
        callback_log("Iniciando automação SIRESP...")
        driver = configurar_navegador()
        driver.set_window_size(1280, 800)
        wait = WebDriverWait(driver, 20)
        
        # --- ETAPA 1: LOGIN ---
        callback_log(f"Acessando {URL_SIRESP_LOGIN}...")
        driver.get(URL_SIRESP_LOGIN)
        
        wait.until(EC.presence_of_element_located((By.ID, "txtUsuario"))).send_keys(USER)
        driver.find_element(By.ID, "txtSenha").send_keys(PASS)
        
        # CAPTCHA
        callback_log("Resolvendo CAPTCHA...")
        try:
            captcha_elm = driver.find_element(By.ID, "imgCaptcha")
            captcha_png = captcha_elm.screenshot_as_png
            img = Image.open(BytesIO(captcha_png)).convert('L').point(lambda x: 0 if x < 128 else 255, '1')
            text_captcha = "".join(filter(str.isalnum, pytesseract.image_to_string(img).strip()))
            
            callback_log(f"CAPTCHA lido: {text_captcha}")
            driver.find_element(By.ID, "txtCaptcha").send_keys(text_captcha)
        except Exception as e:
            raise Exception(f"Erro no CAPTCHA: {e}")

        driver.find_element(By.ID, "btnEntrar").click()
        
        # --- ETAPA 2: VALIDAÇÃO SECUNDÁRIA (RG/CPF) ---
        callback_log("Verificando validação secundária...")
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Unidade') or contains(text(), 'Nome Usuário')]")))
        
        page_source = driver.page_source
        pergunta = next((p for p in RESPOSTAS_VALIDACAO if p in page_source), None)
        
        if not pergunta:
            raise Exception("Pergunta de segurança não identificada.")
            
        resposta = RESPOSTAS_VALIDACAO[pergunta]
        callback_log(f"Pergunta: '{pergunta}' -> Resposta: {resposta}")
        
        # Encontra o input de texto habilitado
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
        campo_resposta = next((inp for inp in inputs if inp.is_displayed() and inp.is_enabled()), None)
        
        if campo_resposta:
            campo_resposta.clear()
            campo_resposta.send_keys(resposta)
            campo_resposta.send_keys(Keys.ENTER)
        else:
            raise Exception("Campo de resposta não encontrado.")
            
        time.sleep(3) # Aguarda transição
        
        # --- ETAPA 3: RELATÓRIO E DOWNLOAD ---
        callback_log("Acessando área de relatórios...")
        driver.get(URL_RELATORIO)
        
        wait.until(EC.presence_of_element_located((By.NAME, "btn_excel")))
        
        # Filtros: Mês e Ano
        try:
            # Seleciona Mês: Janeiro (value='1' ou texto 'Janeiro')
            sel_mes = Select(driver.find_element(By.XPATH, "//select[contains(@name, 'mes') or contains(@id, 'mes')]"))
            sel_mes.select_by_visible_text("Janeiro")
            
            # Seleciona Ano: 2025
            sel_ano = Select(driver.find_element(By.XPATH, "//select[contains(@name, 'ano') or contains(@id, 'ano')]"))
            sel_ano.select_by_visible_text("2025")
            
            callback_log("Filtros aplicados: Janeiro/2025")
        except Exception as e:
            callback_log(f"Aviso ao filtrar data: {e}")

        callback_log("Clicando em baixar Excel...")
        driver.find_element(By.NAME, "btn_excel").click()
        
        # --- ETAPA 4: ESPERA E CARREGAMENTO DO ARQUIVO ---
        callback_log("Aguardando download completar...")
        timeout = 30
        arquivo_final = None
        
        for _ in range(timeout):
            arquivos = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
            # Filtra arquivos temporários (.crdownload)
            validos = [f for f in arquivos if not f.endswith('.crdownload') and not f.endswith('.tmp')]
            
            if validos:
                arquivo_final = max(validos, key=os.path.getctime)
                break
            time.sleep(1)
            
        if not arquivo_final:
            raise Exception("Tempo limite de download excedido.")
            
        callback_log(f"Download concluído: {os.path.basename(arquivo_final)}")
        
        # --- ETAPA 5: PANDAS ---
        callback_log("Processando arquivo com Pandas...")
        df = carregar_dataframe(arquivo_final, callback_log)
        
        callback_log("-" * 30)
        callback_log("DADOS CARREGADOS COM SUCESSO:")
        # Converte para string formatada para exibir no log do frontend
        preview = df.head().to_string()
        callback_log(preview)
        callback_log("-" * 30)
        
        return True

    except Exception as e:
        callback_log(f"ERRO: {str(e)}")
        if driver:
            try: driver.save_screenshot("erro_full.png")
            except: pass
        return False
    finally:
        if driver:
            driver.quit()