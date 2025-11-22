import time
import os
import pytesseract
from PIL import Image
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Configurações
URL_SIRESP = "https://www.siresp.saude.sp.gov.br/"
USER = "stbastos"
PASS = "Catarina@2016"

def run_siresp_extraction(callback_log):
    """
    Executa a automação do SIRESP.
    callback_log: função para enviar logs de volta ao app.
    """
    driver = None
    try:
        callback_log("Configurando navegador Chrome...")
        
        # Opções do Chrome (Headless para servidores, ou comentado para ver a tela)
        options = webdriver.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # options.add_argument("--headless") # Descomente para rodar sem interface gráfica
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.set_window_size(1280, 800)
        
        callback_log(f"Acessando {URL_SIRESP}...")
        driver.get(URL_SIRESP)
        
        # Aguarda carregamento
        wait = WebDriverWait(driver, 15)
        
        # 1. Preencher Usuário
        callback_log("Preenchendo credenciais...")
        user_field = wait.until(EC.presence_of_element_located((By.ID, "txtUsuario"))) # ID hipotético, ajustar se necessário
        user_field.clear()
        user_field.send_keys(USER)
        
        # 2. Preencher Senha
        pass_field = driver.find_element(By.ID, "txtSenha") # ID hipotético
        pass_field.clear()
        pass_field.send_keys(PASS)
        
        # 3. CAPTCHA OCR
        callback_log("Detectando CAPTCHA...")
        # Localiza a imagem do captcha (ajuste o seletor conforme o site real)
        try:
            captcha_img_element = driver.find_element(By.ID, "imgCaptcha") # ID hipotético
            
            # Tira screenshot apenas do elemento do captcha
            captcha_png = captcha_img_element.screenshot_as_png
            image = Image.open(BytesIO(captcha_png))
            
            # Pré-processamento simples para OCR
            image = image.convert('L') # Escala de cinza
            image = image.point(lambda x: 0 if x < 128 else 255, '1') # Limiarização (preto e branco)
            
            # OCR
            captcha_text = pytesseract.image_to_string(image).strip()
            # Remove caracteres não alfanuméricos comuns em erros de OCR
            captcha_text = "".join(filter(str.isalnum, captcha_text))
            
            callback_log(f"Texto identificado no CAPTCHA: {captcha_text}")
            
            # Preenche CAPTCHA
            captcha_field = driver.find_element(By.ID, "txtCaptcha") # ID hipotético
            captcha_field.send_keys(captcha_text)
            
        except Exception as e:
            callback_log(f"Erro ao processar CAPTCHA: {e}")
            raise e

        # 4. Enviar
        callback_log("Enviando formulário de login...")
        btn_submit = driver.find_element(By.ID, "btnEntrar") # ID hipotético
        btn_submit.click()
        
        # 5. Validação de Login
        time.sleep(5) # Espera resposta
        if "senha inválida" in driver.page_source.lower() or "captcha" in driver.page_source.lower():
            raise Exception("Falha no login. Verifique senha ou CAPTCHA.")
            
        callback_log("Login realizado com sucesso (supostamente).")
        
        # 6. Navegação para Ambulatorial
        callback_log("Navegando para Módulo Ambulatorial...")
        # Aqui entraria a lógica de clicar no menu e baixar o relatório
        # Como não tenho acesso real ao DOM pós-login, paro aqui a simulação.
        
        time.sleep(2)
        callback_log("Extração finalizada (Simulação).")
        
        return True

    except Exception as e:
        callback_log(f"ERRO: {str(e)}")
        return False
    finally:
        if driver:
            driver.quit()