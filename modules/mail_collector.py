# -*- coding: utf-8 -*-
import sys, os, base64, warnings, re, time
import requests
from bs4 import BeautifulSoup
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from database import (get_setting, add_invoice, get_invoices,
                      get_vendors, find_vendor_by_name, update_invoice_status)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
try:
    from webdriver_manager.chrome import ChromeDriverManager
    _USE_WDM = True
except ImportError:
    _USE_WDM = False

FOLDER_ID = "AAMkAGUyNWIyYmU4LTBjM2MtNGM4OS04YTE4LWFhZjQ4ZTY3ZmE4ZAAuAAAAAACB7Z4ydzgUQo6MOiLN9ceFAQD2vFdoTp31Tb13wR9oUYV6AAAABH/bAAA="

TAXBILL_DOMAINS = [
    "taxbill365.com",
    "esero.go.kr",
    "etax.hometax.go.kr",
    "bill.taxinfo.go.kr",
    "bizforms.co.kr",
    "biztalk.go.kr",
    "ktbizoffice.com",
    "bizmeka.com",
    "nts.go.kr",
    "kacpta.or.kr",
    "ncaptax.com",
    "wehago.com",
    "douzone.com",
    "icube.co.kr",
    "e-tax.co.kr",
    "everybill.co.kr",
    "bill36524.com",
    "ktnet.com",
    "kbiz.or.kr",
    "hjpay.com",
    "ezwel.com",
]

def _rsa_encrypt(modulus_hex, exponent_hex, plaintext):
    n = int(modulus_hex, 16)
    e = int(exponent_hex, 16)
    key = RSA.construct((n, e))
    cipher = PKCS1_v1_5.new(key)
    b64_text = base64.b64encode(plaintext.encode("utf-8"))
    return cipher.encrypt(b64_text).hex()

def _make_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    if _USE_WDM:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=opts)
    else:
        driver = webdriver.Chrome(options=opts)
    return driver

def _selenium_login(driver, base_url):
    company_id = get_setting("bizmeka_company") or "obase"
    user_id = get_setting("groupware_id") or ""
    pw = get_setting("groupware_pw") or ""
    driver.get(base_url + "/LoginN.aspx?compid=" + company_id)
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    def val(name):
        t = soup.find("input", {"name": name})
        return t["value"] if t else ""
    mod = val("publicModulus")
    exp = val("publicExponent")
    if not mod:
        raise Exception("RSA 공개키를 가져오지 못했습니다.")
    enc_id = _rsa_encrypt(mod, exp, user_id)
    enc_pw = _rsa_encrypt(mod, exp, pw)
    driver.find_element(By.ID, "TextUserID").send_keys(user_id)
    driver.find_element(By.ID, "TextPassword").send_keys(pw)
    driver.execute_script(
        "document.querySelector('[name=EncryptUserID]').value=arguments[0];"
        "document.querySelector('[name=EncryptPassword]').value=arguments[1];"
        "document.querySelector('[name=Encryptcid]').value=arguments[2];",
        enc_id, enc_pw, company_id
    )
    driver.find_element(By.NAME, "LoginButton").click()
    time.sleep(5)
    if "Login" in driver.current_url:
        raise Exception("그룹웨어 Selenium 로그인 실패")

def _get_session_from_driver(driver, base_url):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"])
    return session

def _get_mail_list_js(driver, base_url, keyword="", max_count=200):
    folder_id = FOLDER_ID
    xml_body = (
        "<DATA>"
        "<FOLDERID>" + folder_id + "</FOLDERID>"
        "<SORTTYPE> ORDER BY &quot;urn:schemas:httpmail:datereceived&quot; DESC</SORTTYPE>"
        "<SEARCH></SEARCH>"
        "<START>0</START><END>" + str(max_count - 1) + "</END>"
        "<VIEWSELECTINDEX>0</VIEWSELECTINDEX>"
        "</DATA>"
    )
    driver.get(base_url + "/myoffice/main/index_myoffice.aspx?funCode=1")
    time.sleep(4)
    js = (
        "var xhr = new XMLHttpRequest();"
        "xhr.open('POST', '/myoffice/ezEmail/remote/mail_get_list_cross.aspx', false);"
        "xhr.setRequestHeader('Content-Type', 'text/xml; charset=utf-8');"
        "xhr.send('" + xml_body.replace("'", "\'") + "');"
        "return xhr.responseText;"
    )
    xml_text = driver.execute_script(js)
    if not xml_text:
        return []
    soup = BeautifulSoup(xml_text, "lxml-xml")
    mails = []
    for resp in soup.find_all("response"):
        href_el = resp.find("href")
        subject_el = resp.find("subject")
        from_el = resp.find("from")
        date_el = resp.find("datereceived")
        if href_el:
            mails.append({
                "href": href_el.get_text(strip=True),
                "subject": subject_el.get_text(strip=True) if subject_el else "",
                "from": from_el.get_text(strip=True) if from_el else "",
                "date": date_el.get_text(strip=True) if date_el else "",
            })
    return mails

def _get_mail_body_html(driver, base_url, mail_id):
    """
    Exchange ActiveSync XML API로 메일 본문 HTML을 가져옵니다.
    mail_id: AAMkAG... 형식의 Exchange mail ID
    """
    try:
        # 방법 1: XML API로 메일 본문 직접 조회
        xml_body = (
            "<DATA>"
            "<MAILID>" + mail_id + "</MAILID>"
            "<BODYTYPE>2</BODYTYPE>"
            "</DATA>"
        )
        js = (
            "var xhr = new XMLHttpRequest();"
            "xhr.open('POST', '/myoffice/ezEmail/remote/mail_get_body.aspx', false);"
            "xhr.setRequestHeader('Content-Type', 'text/xml; charset=utf-8');"
            "xhr.send('" + xml_body.replace("'", "\'").replace("\n","") + "');"
            "return xhr.responseText;"
        )
        xml_text = driver.execute_script(js)
        if xml_text and len(xml_text) > 100:
            soup_xml = BeautifulSoup(xml_text, "lxml-xml")
            body_el = soup_xml.find("body") or soup_xml.find("Body") or soup_xml.find("BODY")
            if body_el:
                body_html = body_el.get_text()
                if len(body_html) > 50:
                    return body_html
            # XML 전체에서 HTML 추출 시도
            if "<html" in xml_text.lower() or "<a " in xml_text.lower():
                return xml_text

        # 방법 2: 메일 읽기 페이지를 Selenium으로 열어서 iframe 내용 추출
        read_url = base_url + "/myoffice/ezEmail/mail_read.aspx?id=" + requests.utils.quote(mail_id)
        driver.get(read_url)
        time.sleep(3)

        # iframe 내부 HTML 추출
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                iframe_html = driver.page_source
                driver.switch_to.default_content()
                if len(iframe_html) > 200 and ("<a " in iframe_html or "http" in iframe_html):
                    return iframe_html
            except Exception:
                driver.switch_to.default_content()
                continue

        # 방법 3: 페이지 전체 소스에서 추출
        page_html = driver.page_source
        if len(page_html) > 500:
            return page_html

        return ""
    except Exception as e:
        print(f"[!] _get_mail_body_html 오류: {e}")
        return ""

def _extract_taxbill_links(html):
    """메일 본문 HTML에서 세금계산서 관련 URL 추출"""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    found = []

    # <a href> 링크에서 추출
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href and href.startswith("http"):
            for domain in TAXBILL_DOMAINS:
                if domain in href:
                    found.append(href)
                    break

    # 정규식으로 텍스트에서 URL 추출 (링크 태그 없는 경우 대비)
    if not found:
        urls = re.findall(r'https?://[^s"'<>][]+', html)
        for url in urls:
            for domain in TAXBILL_DOMAINS:
                if domain in url:
                    found.append(url)
                    break

    # 중복 제거
    seen = set()
    result = []
    for u in found:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result

def _parse_from_mail_body(html):
    """메일 본문에서 세금계산서 링크, 금액, 사업자번호 1차 파싱"""
    result = {
        "taxbill_url": None,
        "amount": None,
        "biz_number": None,
        "supplier_name": None,
    }
    if not html:
        return result

    links = _extract_taxbill_links(html)
    if links:
        result["taxbill_url"] = links[0]

    # 금액 추출 (원, 천원, 만원 등)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    amount_patterns = [
        r'공급가액[^d]*(d[d,]+)',
        r'합계금액[^d]*(d[d,]+)',
        r'총액[^d]*(d[d,]+)',
        r'(d[d,]+)s*원',
    ]
    for pat in amount_patterns:
        m = re.search(pat, text)
        if m:
            try:
                result["amount"] = int(m.group(1).replace(",", ""))
                break
            except Exception:
                pass

    # 사업자번호 추출
    biz_pat = r'(d{3}-d{2}-d{5})'
    biz_m = re.search(biz_pat, text)
    if biz_m:
        result["biz_number"] = biz_m.group(1).replace("-", "")

    return result

def _parse_taxbill_page_generic(driver, url):
    """세금계산서 페이지 범용 파서 - 다양한 공급사 대응"""
    result = {
        "supplier_name": None,
        "supplier_biz_no": None,
        "issue_date": None,
        "total_amount": None,
        "supply_amount": None,
        "tax_amount": None,
        "item_name": None,
        "invoice_number": None,
    }
    try:
        driver.get(url)
        time.sleep(3)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()

        # 사업자번호
        biz_matches = re.findall(r'(d{3}-d{2}-d{5})', text)
        if biz_matches:
            result["supplier_biz_no"] = biz_matches[0].replace("-", "")

        # 금액 파싱
        amount_patterns = [
            (r'공급가액[^d]*(d[d,]+)', "supply_amount"),
            (r'세액[^d]*(d[d,]+)', "tax_amount"),
            (r'합계[^d]*(d[d,]+)', "total_amount"),
        ]
        for pat, key in amount_patterns:
            m = re.search(pat, text)
            if m:
                try:
                    result[key] = int(m.group(1).replace(",", ""))
                except Exception:
                    pass

        if result["supply_amount"] and result["tax_amount"] and not result["total_amount"]:
            result["total_amount"] = result["supply_amount"] + result["tax_amount"]

        # 날짜 파싱
        date_m = re.search(r'(d{4})[년/-.](d{1,2})[월/-.](d{1,2})', text)
        if date_m:
            result["issue_date"] = f"{date_m.group(1)}-{date_m.group(2).zfill(2)}-{date_m.group(3).zfill(2)}"

        # 공급자명
        name_patterns = [
            r'공급자[^
]*법인명[^
]*([가-힣A-Za-z(주)(주식회사)s]{2,20})',
            r'상호[^
]*([가-힣A-Za-z(주)(주식회사)s]{2,20})',
        ]
        for pat in name_patterns:
            m = re.search(pat, text)
            if m:
                result["supplier_name"] = m.group(1).strip()
                break

    except Exception as e:
        print(f"[!] _parse_taxbill_page_generic 오류: {e}")
    return result

def run_pipeline(log_fn=None):
    """메인 파이프라인: 로그인 → 메일 조회 → 세금계산서 파싱 → DB 저장"""
    def log(msg):
        if log_fn:
            log_fn(msg)
        else:
            print(msg)

    driver = None
    results = {"processed": 0, "saved": 0, "errors": 0, "skipped": 0}

    try:
        base_url = get_setting("groupware_url") or "https://www.bizmeka.com"
        log(f"[*] 그룹웨어 URL: {base_url}")

        driver = _make_driver(headless=True)
        _selenium_login(driver, base_url)
        log("[*] 그룹웨어 로그인 완료")

        mails = _get_mail_list_js(driver, base_url, max_count=200)
        log(f"[*] 메일 {len(mails)}건 조회")

        vendors = get_vendors()
        vendor_map = {}
        for v in vendors:
            biz = str(v.get("biz_number", "")).replace("-", "")
            if biz:
                vendor_map[biz] = v

        for i, mail in enumerate(mails):
            subject = mail.get("subject", "")
            mail_id = mail.get("href", "")

            # 세금계산서 관련 키워드 필터
            keywords = ["세금계산서", "tax", "계산서", "invoice"]
            if not any(kw.lower() in subject.lower() for kw in keywords):
                continue

            log(f"[{i+1}] 처리 중: {subject[:50]}")
            results["processed"] += 1

            try:
                html = _get_mail_body_html(driver, base_url, mail_id)
                if not html or len(html) < 50:
                    log(f"  -> 본문 없음 스킵")
                    results["skipped"] += 1
                    continue

                parsed = _parse_from_mail_body(html)
                taxbill_url = parsed.get("taxbill_url")

                if not taxbill_url:
                    log(f"  -> 세금계산서 링크 없음 스킵")
                    results["skipped"] += 1
                    continue

                log(f"  -> 링크 발견: {taxbill_url[:80]}")
                invoice_data = _parse_taxbill_page_generic(driver, taxbill_url)

                biz_no = invoice_data.get("supplier_biz_no", "")
                vendor = vendor_map.get(biz_no) if biz_no else None

                save_data = {
                    "mail_subject": subject,
                    "mail_id": mail_id,
                    "taxbill_url": taxbill_url,
                    "vendor_id": vendor["id"] if vendor else None,
                    "supplier_name": invoice_data.get("supplier_name") or (vendor["name"] if vendor else ""),
                    "supplier_biz_no": biz_no,
                    "issue_date": invoice_data.get("issue_date", ""),
                    "total_amount": invoice_data.get("total_amount", 0) or 0,
                    "supply_amount": invoice_data.get("supply_amount", 0) or 0,
                    "tax_amount": invoice_data.get("tax_amount", 0) or 0,
                    "item_name": invoice_data.get("item_name", ""),
                    "invoice_number": invoice_data.get("invoice_number", ""),
                    "status": "pending",
                }
                add_invoice(save_data)
                log(f"  -> 저장 완료: {save_data['supplier_name']} / {save_data['total_amount']:,}원")
                results["saved"] += 1

            except Exception as e:
                log(f"  -> 오류: {e}")
                results["errors"] += 1
                continue

        log(f"[*] 완료 - 처리:{results['processed']} 저장:{results['saved']} 오류:{results['errors']} 스킵:{results['skipped']}")
        return True, results

    except Exception as e:
        log(f"[!] 파이프라인 오류: {e}")
        return False, str(e)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

def run_full_pipeline(log_fn=None):
    return run_pipeline(log_fn=log_fn)

def test_connection(target="groupware"):
    driver = None
    try:
        base_url = get_setting("groupware_url") or "https://www.bizmeka.com"
        driver = _make_driver(headless=True)
        _selenium_login(driver, base_url)
        return True, "그룹웨어 로그인 성공"
    except Exception as e:
        try:
            if driver: driver.quit()
        except Exception:
            pass
        return False, str(e)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
