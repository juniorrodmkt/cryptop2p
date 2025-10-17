# cripto.py
# -*- coding: utf-8 -*-
"""
API FastAPI + HTML (no mesmo arquivo) para:
- Executar o fluxo AlfredP2P via Selenium (headless)
- Extrair o PIX Copia-e-Cola
- Gerar QR (PNG) em memória
- Servir um HTML que chama a API e exibe o QR + payload

Rodar:
  pip install fastapi uvicorn selenium undetected-chromedriver qrcode[pil] opencv-python
  uvicorn cripto:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import random
import sys
import time
from typing import Optional
from decimal import Decimal, InvalidOperation

# --- FastAPI / Starlette ---
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

# --- Selenium e afins ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, JavascriptException

# --- QRCode ---
import qrcode

# -------------------- Constantes --------------------
URL_HOME = "https://www.alfredp2p.io/pt"
WALLET_ADDRESS = "14xB8dpLNodKmWPwdFxDcvv45QECtkRhhV"
BRL_AMOUNT_DEFAULT = "500"  # valor padrão/fallback; FRONT envia dinamicamente

# Credenciais FIXAS (exemplo)
CREDENTIAL_USER = "usuario20032"
CREDENTIAL_PASS = "vitinho90gta"

# Arquivos locais (apenas se quiser salvar; a API retorna base64)
PNG_PATH = "pix_qrcode.png"
HTML_SNAPSHOT = "qrcode.html"  # opcional: gravamos um snapshot do HTML gerado


# -------------------- Helpers --------------------
def text_xpath_equals_ci(text: str) -> str:
    return f'[translate(normalize-space(.),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz")="{text.lower()}"]'

def human_sleep(a=0.08, b=0.18):
    time.sleep(random.uniform(a, b))

def salvar_qrcode_png(payload: str, arquivo_png=PNG_PATH, box_size=10, border=4) -> str:
    if not payload or len(payload.strip()) < 20:
        print("[ERRO] Payload inválido para QR.")
        return ""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload.strip())
    qr.make(fit=True)
    img = qr.make_image()
    img.save(arquivo_png)
    print(f"[OK] QR Code salvo em: {arquivo_png}")
    return arquivo_png

def qrcode_png_bytes(payload: str, box_size=10, border=4) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload.strip())
    qr.make(fit=True)
    img = qr.make_image()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def human_type(elem, text, a=0.03, b=0.10):
    for ch in text:
        elem.send_keys(ch)
        human_sleep(a, b)

def wait_visible(driver, by, expr, timeout=12):
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, expr)))

def safe_click(driver, elem, timeout=8):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
    except Exception:
        pass
    try:
        WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(elem))
        elem.click()
        return
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", elem)
        return
    except Exception:
        pass
    ActionChains(driver).move_to_element(elem).pause(0.05).click().perform()


# -------------------- Driver (stealth) --------------------
def build_driver(headless=True):
    # tenta undetected-chromedriver
    try:
        import undetected_chromedriver as uc
        opts = uc.ChromeOptions()
        if headless:
            opts.add_argument("--headless=new")
        _common_chrome_opts(opts)
        driver = uc.Chrome(options=opts, use_subprocess=True)
        try:
            driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": "America/Recife"})
        except Exception:
            pass
        apply_stealth_js(driver)
        driver.set_page_load_timeout(60)
        return driver
    except Exception:
        pass  # cai no Selenium padrão

    # Chrome padrão
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    _common_chrome_opts(opts)
    driver = webdriver.Chrome(options=opts)
    try:
        driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": "America/Recife"})
    except Exception:
        pass
    apply_stealth_js(driver)
    driver.set_page_load_timeout(60)
    return driver

def _common_chrome_opts(opts):
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-infobars")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--lang=pt-BR")
    opts.add_argument("--window-size=1280,900")
    opts.page_load_strategy = "eager"
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )

def apply_stealth_js(driver):
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": r"""
// webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
// languages
Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR','pt','en-US'] });
// plugins
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
// platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
// chrome runtime
window.chrome = window.chrome || { runtime: {} };
// permissions
const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
  window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters)
  );
}
// UA-CH mock
try {
  Object.defineProperty(navigator, 'userAgentData', { get: () => ({ brands: [{brand:'Chromium',version:'123'}], mobile: false, platform: 'Windows' }) });
} catch(e) {}
// WebGL
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
  if (parameter === 37445) return 'Intel Inc.';
  if (parameter === 37446) return 'Intel Iris OpenGL Engine';
  return getParameter.call(this, parameter);
};
// Canvas noise
const toDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function() {
  const ctx = this.getContext('2d');
  try {
    const shift = 0.001;
    const imgData = ctx.getImageData(0, 0, this.width, this.height);
    for (let i = 0; i < imgData.data.length; i += 4) { imgData.data[i] += shift; }
    ctx.putImageData(imgData, 0, 0);
  } catch(e) {}
  return toDataURL.apply(this, arguments);
};
            """
        })
    except Exception:
        pass


# -------------------- Passos do fluxo --------------------
def impedir_popup_mesma_aba(driver):
    try:
        driver.execute_script("""
          (function(){
            try{
              const _open = window.open;
              window.open = function(url){ try{ if(url) location.href = url; }catch(e){} return null; };
            }catch(e){}
          })();
        """)
        driver.execute_script("""document.querySelectorAll('a[target="_blank"]').forEach(a=>a.removeAttribute('target'));""")
    except Exception:
        pass

def aceitar_cookies_se_existir(driver):
    for rotulo in ["Aceitar", "Aceito", "Concordo", "OK", "Prosseguir"]:
        xpath_btn = f"//button{ text_xpath_equals_ci(rotulo) }"
        try:
            btn = WebDriverWait(driver, 1.2).until(EC.element_to_be_clickable((By.XPATH, xpath_btn)))
            safe_click(driver, btn); break
        except Exception:
            continue


def normalize_brl_amount(amount_in: str | float | int | None) -> str:
    """Normaliza valor BRL vindo do FRONT ("1000,50", "1.000,50", 1000.5, etc.)
    Retorna string com ponto decimal, 2 casas. Lança HTTPException(422) se inválido.
    """
    if amount_in is None:
        raise HTTPException(status_code=422, detail="Informe o valor em BRL (amount).")
    s = str(amount_in).strip()
    if not s:
        raise HTTPException(status_code=422, detail="Valor em BRL vazio.")
    # remove símbolo e espaços
    s = s.replace("R$", "").replace(" ", "")
    # trata milhar brasileiro e decimal
    if "," in s and "." in s:
        # casos tipo 1.234,56 -> remove ponto de milhar
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        val = Decimal(s)
    except InvalidOperation:
        raise HTTPException(status_code=422, detail="Valor em BRL inválido.")
    if val <= 0:
        raise HTTPException(status_code=422, detail="O valor deve ser maior que zero.")
    # opcional: faixas
    if val < Decimal("5"):
        raise HTTPException(status_code=422, detail="Valor mínimo é R$ 5,00.")
    if val > Decimal("200000"):
        raise HTTPException(status_code=422, detail="Valor máximo permitido excedido.")
    return f"{val:.2f}"  # sempre com 2 casas decimais


def preencher_valor_brl_e_prosseguir(driver, valor: str, timeout=12):
    # "valor" já vem normalizado (p.ex. "500.00")
    try:
        input_valor = wait_visible(driver, By.CSS_SELECTOR, 'input[placeholder="Digite o valor em BRL"]', timeout)
    except TimeoutException:
        input_valor = wait_visible(driver, By.CSS_SELECTOR, 'input[name="fiatAmount"]', timeout)

    safe_click(driver, input_valor)
    try: input_valor.clear()
    except: pass
    # digita sem separador de milhar; mantém ponto decimal
    human_type(input_valor, valor)
    try: input_valor.send_keys("\t")
    except: pass

    try:
        btn = wait_visible(driver, By.XPATH, f"//button{ text_xpath_equals_ci('Prosseguir') }", timeout)
    except TimeoutException:
        btn = wait_visible(driver, By.XPATH, "//button[contains(normalize-space(.),'Prosseguir')]", timeout)
    safe_click(driver, btn)

    try:
        WebDriverWait(driver, 10).until(lambda d: "/checkout" in d.current_url)
    except TimeoutException:
        for css in ('input[placeholder="Selecione a Rede"]', 'input[placeholder="Selecione o Método de Pagamento"]'):
            try:
                wait_visible(driver, By.CSS_SELECTOR, css, 4)
                break
            except TimeoutException:
                pass


def selecionar_rede_onchain(driver, timeout=10):
    try:
        rede_input = wait_visible(driver, By.CSS_SELECTOR, 'input[placeholder="Selecione a Rede"]', timeout)
        safe_click(driver, rede_input)
    except TimeoutException:
        try:
            container = driver.find_element(By.CSS_SELECTOR, "div.flex.justify-center.items-center.relative.w-full")
            btn = container.find_element(By.XPATH, ".//button[contains(@class,'absolute') and contains(@class,'right-4')]")
            safe_click(driver, btn)
        except Exception:
            rede_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="Selecione a Rede"][readonly]')
            safe_click(driver, rede_input)

    onchain_x = ".//li[.//span[normalize-space(text())='Onchain'] or .//img[@alt='Onchain']][1]"
    li = driver.find_element(By.XPATH, onchain_x)
    safe_click(driver, li)
    human_sleep()


def selecionar_metodo_pagamento_pix(driver, timeout=10):
    input_mp = wait_visible(driver, By.CSS_SELECTOR, 'input[placeholder="Selecione o Método de Pagamento"]', timeout)
    try:
        safe_click(driver, input_mp)
    except Exception:
        try:
            container = input_mp.find_element(By.XPATH, "./ancestor::div[contains(@class,'relative') and contains(@class,'w-full')]")
            btn = container.find_element(By.XPATH, ".//button[contains(@class,'absolute') and contains(@class,'right-4')]")
            safe_click(driver, btn)
        except Exception:
            safe_click(driver, input_mp)

    pix_xpath = (
        "//li[not(contains(@class,'opacity-50')) and not(contains(@class,'cursor-not-allowed'))]"
        "[.//span[normalize-space()='PIX']][1]"
    )
    li_pix = driver.find_element(By.XPATH, pix_xpath)
    safe_click(driver, li_pix)
    human_sleep()


def preencher_carteira(driver, address: str, timeout=8):
    input_wallet = wait_visible(driver, By.CSS_SELECTOR, 'input[placeholder="Carteira"]', timeout)
    safe_click(driver, input_wallet)
    try: input_wallet.clear()
    except: pass
    try:
        human_type(input_wallet, address)
    except Exception:
        driver.execute_script("""
            const el = arguments[0], val = arguments[1];
            el.focus(); el.value = '';
            const set = (v)=>{ el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); };
            set(val); el.blur(); el.dispatchEvent(new Event('change',{bubbles:true}));
        """, input_wallet, address)
    try: input_wallet.send_keys("\t")
    except: pass


def preencher_credenciais_fixas(driver, timeout=8):
    input_user = wait_visible(driver, By.CSS_SELECTOR, 'input[placeholder="Usuário (sem espaços)"]', timeout)
    input_pass = wait_visible(driver, By.CSS_SELECTOR, 'input[placeholder="Senha (sem espaços)"]', timeout)

    safe_click(driver, input_user)
    try: input_user.clear()
    except: pass
    human_type(input_user, CREDENTIAL_USER)
    try: input_user.send_keys("\t")
    except: pass

    safe_click(driver, input_pass)
    try: input_pass.clear()
    except: pass
    human_type(input_pass, CREDENTIAL_PASS)
    try: input_pass.send_keys("\t")
    except: pass


def marcar_checkboxes_de_aceite(driver, timeout=6):
    textos = ["Aceito as taxas", "Aceito os termos e condições"]
    for texto in textos:
        label = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, f"//label[contains(@class,'flex') and contains(@class,'items-center')][.//*[contains(normalize-space(.),'{texto}')]]"))
        )
        checkbox = label.find_element(By.XPATH, ".//input[@type='checkbox' and contains(@class,'sr-only')]")
        toggle = label.find_element(By.XPATH, ".//div[contains(@class,'relative')][.//input[@type='checkbox']]")
        track  = toggle.find_element(By.XPATH, ".//div[contains(@class,'w-10') and contains(@class,'h-5')]")
        knob   = toggle.find_element(By.XPATH, ".//div[contains(@class,'absolute') and contains(@class,'w-4') and contains(@class,'h-4')]")

        try: driver.execute_script("arguments[0].scrollIntoView({block:'center'});", toggle)
        except: pass

        if checkbox.is_selected():
            continue

        for target in (track, knob, checkbox):
            try:
                safe_click(driver, target)
                human_sleep(0.05, 0.12)
                if checkbox.is_selected():
                    break
            except Exception:
                continue

        if not checkbox.is_selected():
            try:
                driver.execute_script(
                    """
                    const el = arguments[0];
                    if (!el.checked) {
                        el.checked = true;
                        el.dispatchEvent(new Event('input',{bubbles:true}));
                        el.dispatchEvent(new Event('change',{bubbles:true}));
                    }
                """,
                    checkbox,
                )
            except JavascriptException:
                pass


def clicar_finalizar_pagamento(driver, timeout=15):
    try:
        btn = wait_visible(driver, By.XPATH, f"//button{ text_xpath_equals_ci('Finalizar Pagamento') }", timeout)
    except TimeoutException:
        btn = wait_visible(driver, By.XPATH, "//button[contains(normalize-space(.),'Finalizar') and contains(normalize-space(.),'Pagamento')]", timeout)
    safe_click(driver, btn)
    try:
        WebDriverWait(driver, 7).until(lambda d: any(s in d.page_source.lower() for s in ["qr", "pix", "copia e cola", "aguardando", "pagamento", "pedido"]))
    except TimeoutException:
        pass


def marcar_wallet_confirmation_apos_finalizar(driver, timeout=15):
    checkbox = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, "walletConfirmation")))
    try: driver.execute_script("arguments[0].scrollIntoView({block:'center'});", checkbox)
    except: pass
    if not checkbox.is_selected():
        try: safe_click(driver, checkbox)
        except: pass
    if not checkbox.is_selected():
        try:
            label = driver.find_element(By.XPATH, "//label[@for='walletConfirmation']")
            safe_click(driver, label)
        except Exception:
            pass
    if not checkbox.is_selected():
        driver.execute_script(
            """
            const el = arguments[0];
            if (!el.checked) {
                el.checked = true;
                el.dispatchEvent(new Event('input',{bubbles:true}));
                el.dispatchEvent(new Event('change',{bubbles:true}));
            }
        """,
            checkbox,
        )


def clicar_confirmar(driver, timeout=15):
    try:
        btn = wait_visible(driver, By.XPATH, f"//button{ text_xpath_equals_ci('Confirmar') }", timeout)
    except TimeoutException:
        btn = wait_visible(driver, By.XPATH, "//button[contains(normalize-space(.),'Confirmar')]", timeout)
    safe_click(driver, btn)
    try:
        WebDriverWait(driver, 7).until(lambda d: any(p in d.page_source.lower() for p in
            ["sucesso", "concluido", "concluído", "pedido", "comprovante", "resumo", "aguarde", "processando", "gerando", "enviando"]))
    except TimeoutException:
        pass


# -------------------- Extrair QR / Copia-e-Cola --------------------
def extrair_qrcode_pix(driver, timeout=25, arquivo_png="pix_qr.png") -> Optional[str]:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH,
                "//svg[@role='img'] | //canvas | //img[contains(translate(@alt,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'qr') or contains(translate(@alt,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pix')]"
            ))
        )
    except TimeoutException:
        pass

    # 1) data-clipboard-text
    try:
        copy_btn = driver.find_element(By.CSS_SELECTOR, "[data-clipboard-text]")
        payload = (copy_btn.get_attribute("data-clipboard-text") or "").strip()
        if len(payload) > 30:
            try: salvar_qrcode_png(payload, "pix_qrcode.png")
            except Exception: pass
            return payload
    except NoSuchElementException:
        pass

    # 2) inputs/textarea
    candidatos = []
    candidatos += driver.find_elements(By.XPATH, "//textarea[string-length(normalize-space(.))>30]")
    candidatos += driver.find_elements(By.XPATH, "//input[(not(@type) or @type='text' or @type='search' or @type='tel') and string-length(@value)>30]")

    for el in candidatos:
        val = (el.get_attribute("value") or el.text or "").strip()
        if len(val) > 30 and (val.startswith("000201") or "BR.GOV.BCB.PIX" in val.upper()):
            try: salvar_qrcode_png(val, "pix_qrcode.png")
            except Exception: pass
            return val

    # 3) botão copiar
    try:
        btn_cc = driver.find_element(By.XPATH,
            "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'copia e cola') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'copiar')]"
        )
        safe_click(driver, btn_cc)
        human_sleep()
        return extrair_qrcode_pix(driver, timeout=5, arquivo_png=arquivo_png)
    except NoSuchElementException:
        pass

    # 4) screenshot + decode opcional
    qr_elem = None
    for xp in ["//svg[@role='img']",
               "//canvas",
               "//img[contains(translate(@alt,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'qr') or contains(translate(@alt,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pix')]"]:
        try:
            qr_elem = driver.find_element(By.XPATH, xp)
            break
        except NoSuchElementException:
            continue

    if qr_elem:
        try:
            qr_elem.screenshot(arquivo_png)
        except Exception:
            pass

        try:
            import cv2
            img = cv2.imread(arquivo_png)
            if img is not None:
                det = cv2.QRCodeDetector()
                data, pts, _ = det.detectAndDecode(img)
                if data:
                    return data
        except Exception:
            pass

        try:
            with open(arquivo_png, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
                print("QR_BASE64:", "data:image/png;base64," + b64)
        except Exception:
            pass

    return None


# -------------------- Fluxo principal (bloqueante) --------------------
def abrir_checkout(headless=True, brl_amount: str = BRL_AMOUNT_DEFAULT) -> Optional[str]:
    driver = build_driver(headless=headless)
    payload = None
    try:
        driver.get(URL_HOME)
        impedir_popup_mesma_aba(driver)
        aceitar_cookies_se_existir(driver)

        preencher_valor_brl_e_prosseguir(driver, valor=brl_amount)
        try: driver.save_screenshot("home_brl.png")
        except Exception: pass

        selecionar_rede_onchain(driver)
        selecionar_metodo_pagamento_pix(driver)
        preencher_carteira(driver, WALLET_ADDRESS)
        preencher_credenciais_fixas(driver)
        marcar_checkboxes_de_aceite(driver)

        clicar_finalizar_pagamento(driver)
        marcar_wallet_confirmation_apos_finalizar(driver)
        clicar_confirmar(driver)

        payload = extrair_qrcode_pix(driver, timeout=25, arquivo_png="pix_qr.png")

        try: driver.save_screenshot("fluxo_completo.png")
        except Exception: pass
    finally:
        try: driver.quit()
        except Exception: pass
    return payload


# -------------------- HTML servido pela API --------------------
def build_front_html() -> str:
    # Página mínima que chama POST /api/generate e exibe o QR + payload
    return """<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\">
  <title>PIX QRCode</title>
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <style>
    :root { color-scheme: light dark; }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 24px; }
    .card { max-width: 560px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 14px; padding: 24px; box-shadow: 0 2px 10px rgba(0,0,0,.06); }
    .row { display:flex; gap: 12px; align-items:center; }
    .muted { color:#6b7280; font-size: 14px; }
    label { display:block; margin-top: 12px; font-weight: 600; }
    input[type=\"text\"] { width:100%; padding:12px; border-radius:8px; border:1px solid #ddd; font-size:16px; }
    #qr { display:block; margin: 16px auto; width: 280px; height: 280px; border:1px solid #e5e7eb; border-radius: 8px; object-fit:contain; }
    textarea { width:100%; min-height:120px; padding:12px; border-radius:8px; border:1px solid #ddd; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    button { margin-top: 12px; padding: 10px 16px; border-radius: 10px; border: 0; background: #111827; color: #fff; cursor: pointer; }
    button[disabled] { opacity: .6; cursor: not-allowed; }
    .spinner { display:inline-block; width:16px; height:16px; border:2px solid currentColor; border-right-color:transparent; border-radius:50%; animation: spin 0.6s linear infinite; vertical-align: -3px; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>Pagamento via PIX</h1>
    <p class=\"muted\">Informe o valor e clique em \"Gerar QR\" para iniciar o fluxo.</p>

    <label for=\"amount\">Valor (BRL)</label>
    <input id=\"amount\" type=\"text\" inputmode=\"decimal\" pattern=\"[0-9.,]*\" placeholder=\"Ex.: 500,00\" value=\"500,00\" />

    <div class=\"row\">
      <button id=\"genBtn\">Gerar QR</button>
      <span id=\"status\" class=\"muted\"></span>
    </div>
    <img id=\"qr\" alt=\"PIX QRCode\" />
    <label for=\"pix\" class=\"muted\">PIX Copia-e-Cola</label>
    <textarea id=\"pix\" readonly></textarea>
    <div class=\"row\">
      <button id=\"copyBtn\">Copiar código</button>
      <span id=\"msg\" class=\"muted\"></span>
    </div>
  </div>

  <script>
    const genBtn = document.getElementById('genBtn');
    const copyBtn = document.getElementById('copyBtn');
    const statusEl = document.getElementById('status');
    const msgEl = document.getElementById('msg');
    const qrImg = document.getElementById('qr');
    const ta = document.getElementById('pix');
    const amountEl = document.getElementById('amount');

    function setStatus(txt, loading=false){
      statusEl.innerHTML = loading ? '<span class=\"spinner\"></span> ' + txt : txt;
    }

    genBtn.addEventListener('click', async () => {
      const amount = (amountEl.value || '').trim();
      if(!amount){ setStatus('Informe um valor válido.'); return; }
      genBtn.disabled = true; setStatus('Gerando QR (pode levar alguns segundos)...', true);
      msgEl.textContent = ''; qrImg.removeAttribute('src'); ta.value='';
      try {
        const res = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ amount })
        });
        if(!res.ok){
          const err = await res.json().catch(()=>({detail:'Erro'}));
          throw new Error(err.detail || ('HTTP ' + res.status));
        }
        const data = await res.json();
        qrImg.src = data.png_data_url;
        ta.value = data.payload;
        setStatus('Pronto!');
      } catch(e){
        setStatus('Falhou: ' + (e.message || e));
      } finally {
        genBtn.disabled = false;
      }
    });

    copyBtn.addEventListener('click', async () => {
      ta.select(); ta.setSelectionRange(0, 99999);
      try {
        await navigator.clipboard.writeText(ta.value);
        msgEl.textContent = 'Copiado!';
        setTimeout(()=>{ msgEl.textContent=''; }, 3000);
      } catch(e) {
        msgEl.textContent = 'Não foi possível copiar automaticamente.';
      }
    });
  </script>
</body>
</html>"""


# -------------------- ASGI App --------------------
app = FastAPI(title="Cripto QR API", version="1.1.0")
GEN_LOCK = asyncio.Lock()

@app.get("/", response_class=HTMLResponse)
async def root():
    # Serve o HTML que consome a API
    html = build_front_html()
    # salva um snapshot (opcional)
    try:
        with open(HTML_SNAPSHOT, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass
    return HTMLResponse(html)

@app.get("/api/health")
async def health():
    return {"ok": True}

@app.post("/api/generate")
async def api_generate(data: dict = Body(default=None)):
    # evita concorrência múltipla (Selenium/Chrome não gostam)
    async with GEN_LOCK:
        # valida e normaliza o valor vindo do FRONT
        try:
            brl_amount = normalize_brl_amount((data or {}).get("amount"))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Valor inválido: {e}")

        try:
            # executa fluxo bloqueante em threadpool, com timeout global
            payload = await asyncio.wait_for(
                run_in_threadpool(lambda: abrir_checkout(headless=True, brl_amount=brl_amount)),
                timeout=240
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Tempo excedido ao gerar o QR/PIX.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Falha ao executar o fluxo: {e}")

        if not payload or len(payload.strip()) < 20:
            raise HTTPException(status_code=500, detail="Não foi possível obter o PIX Copia-e-Cola.")

        # Gera PNG em memória e também grava arquivo local (opcional)
        png_bytes = qrcode_png_bytes(payload)
        try:
            salvar_qrcode_png(payload, PNG_PATH)
        except Exception:
            pass

        data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
        # opcional: também escreve um HTML estático de snapshot com esse conteúdo
        try:
            _html = f"<img src='{data_url}' alt='qr'><pre>{payload}</pre>"
            with open(HTML_SNAPSHOT, "w", encoding="utf-8") as f:
                f.write(_html)
        except Exception:
            pass

        return JSONResponse({
            "ok": True,
            "payload": payload,
            "png_data_url": data_url,
            "png_file": os.path.abspath(PNG_PATH),
            "amount": brl_amount,
        })


# Execução direta opcional: uvicorn embutido
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("cripto:app", host="0.0.0.0", port=8000, reload=False)
