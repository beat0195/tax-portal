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
    user_id    = get_setting("groupware_id") or ""
    pw         = get_setting("groupware_pw") or ""
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
        "xhr.send('" + xml_body.replace("'", "\\'") + "');"
        "return xhr.responseText;"
    )
    xml_text = driver.execute_script(js)
    if not xml_text:
        return []
    soup = BeautifulSoup(xml_text, "lxml-xml")
    mails = []
    for resp in soup.find_all("response"):
        subject = (resp.find("subject") or type("", (), {"text": ""})()).text
        if keyword and keyword not in subject:
            continue
        href = (resp.find("href") or type("", (), {"text": ""})()).text
        date = (resp.find("receivedt") or type("", (), {"text": ""})()).text
        sender_el = resp.find("from") or resp.find("sender")
        sender = sender_el.text if sender_el else ""
        mails.append({"subject": subject, "href": href, "date": date, "sender": sender})
    return mails

def _get_mail_body_html(driver, base_url, mail_href):
    try:
        js = (
            "var xhr = new XMLHttpRequest();"
            "xhr.open('POST', '/myoffice/ezEmail/remote/mail_view_cross.aspx', false);"
            "xhr.setRequestHeader('Content-Type', 'text/xml; charset=utf-8');"
            "var body = '<DATA><HREF>" + mail_href.replace("'", "\\'") + "</HREF></DATA>';"
            "xhr.send(body);"
            "return xhr.responseText;"
        )
        xml_text = driver.execute_script(js)
        if xml_text:
            soup = BeautifulSoup(xml_text, "lxml-xml")
            body_el = soup.find("body") or soup.find("BODY") or soup.find("htmlbody")
            if body_el:
                return body_el.text
        driver.get(base_url + "/myoffice/ezEmail/mail_view.aspx?href=" + mail_href)
        time.sleep(3)
        return driver.page_source
    except Exception:
        return ""

def _parse_from_mail_body(html_text):
    result = {
        "supplier_biz_no": "", "supplier_name": "", "issue_date": "",
        "supply_amount": 0,    "tax_amount": 0,    "total_amount": 0,
        "item_name": "",       "taxbill_links": [],
    }
    if not html_text:
        return result
    soup = BeautifulSoup(html_text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(d in href for d in TAXBILL_DOMAINS):
            result["taxbill_links"].append(href)
        elif re.search(r"taxbill|tax_bill|etax|계산서|bill", href, re.I):
            result["taxbill_links"].append(href)
    result["taxbill_links"] = list(dict.fromkeys(result["taxbill_links"]))
    text = soup.get_text(separator="\n")
    buyer_biz = (get_setting("buyer_biz_no") or "").replace("-", "").replace(" ", "")
    biz_nos = re.findall(r"\d{3}-\d{2}-\d{5}", text)
    for bno in biz_nos:
        cleaned = bno.replace("-", "")
        if cleaned != buyer_biz:
            result["supplier_biz_no"] = cleaned
            break
    if not result["supplier_biz_no"] and biz_nos:
        result["supplier_biz_no"] = biz_nos[0].replace("-", "")
    def find_amount(labels):
        for lbl in labels:
            m = re.search(lbl + r"[^\d]{0,15}([1-9][\d,]{2,})", text)
            if m:
                v = int(m.group(1).replace(",", ""))
                if v > 0:
                    return v
        return 0
    result["total_amount"]  = find_amount(["합계금액","청구금액","합 계","합계","총금액","total"])
    result["supply_amount"] = find_amount(["공급가액","공급금액"])
    result["tax_amount"]    = find_amount(["세액","부가세","vat"])
    if not result["total_amount"] and result["supply_amount"]:
        result["total_amount"] = result["supply_amount"] + result["tax_amount"]
    if not result["supply_amount"] and result["total_amount"] and result["tax_amount"]:
        result["supply_amount"] = result["total_amount"] - result["tax_amount"]
    m = re.search(r"(\d{4})[\-./년]\s*(\d{1,2})[\-./월]\s*(\d{1,2})", text)
    if m:
        result["issue_date"] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    for pattern in [r"공급자[\s\S]{0,10}상호[^가-힣\w]{0,5}([가-힣\w]{2,20})",
                    r"상호\s*[:\uff1a]?\s*([가-힣\w]{2,20})",
                    r"회사명\s*[:\uff1a]?\s*([가-힣\w]{2,20})"]:
        m = re.search(pattern, text)
        if m:
            result["supplier_name"] = m.group(1).strip()
            break
    for pattern in [r"품목\s*[:\uff1a]?\s*([가-힣\w\s]{2,30})",
                    r"품명\s*[:\uff1a]?\s*([가-힣\w\s]{2,30})"]:
        m = re.search(pattern, text)
        if m:
            result["item_name"] = m.group(1).strip()[:30]
            break
    return result

def _is_taxbill_link(url):
    if any(d in url for d in TAXBILL_DOMAINS):
        return True
    return bool(re.search(r"taxbill|tax_bill|etax|계산서", url, re.I))

def _parse_taxbill_page_generic(driver, taxbill_url, buyer_biz=""):
    import datetime
    result = {
        "supplier_biz_no": "", "supplier_name": "", "issue_date": "",
        "supply_amount": 0, "tax_amount": 0, "total_amount": 0,
        "item_name": "", "pdf_path": "", "error": "",
    }
    try:
        original_handle = driver.current_window_handle
        all_handles_before = set(driver.window_handles)
        driver.get(taxbill_url)
        time.sleep(4)
        new_handles = set(driver.window_handles) - all_handles_before
        if new_handles:
            driver.switch_to.window(new_handles.pop())
            time.sleep(3)
        buyer_biz_clean = buyer_biz.replace("-", "").replace(" ", "")
        frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
        if frames and buyer_biz_clean and len(buyer_biz_clean) >= 10:
            try:
                driver.switch_to.frame(frames[0])
                time.sleep(1)
                try:
                    el1 = driver.find_element(By.NAME, "CORP_NO1")
                    el2 = driver.find_element(By.NAME, "CORP_NO2")
                    el3 = driver.find_element(By.NAME, "CORP_NO3")
                    ActionChains(driver).click(el1).send_keys(buyer_biz_clean[0:3]).perform(); time.sleep(0.3)
                    ActionChains(driver).click(el2).send_keys(buyer_biz_clean[3:5]).perform(); time.sleep(0.3)
                    ActionChains(driver).click(el3).send_keys(buyer_biz_clean[5:10]).perform(); time.sleep(0.3)
                except Exception:
                    pass
                try:
                    single = driver.find_element(By.CSS_SELECTOR,
                        "input[name*='corp'], input[name*='biz'], input[name*='bizno'], input[id*='bizno']")
                    single.clear()
                    single.send_keys(buyer_biz_clean[:10])
                    time.sleep(0.3)
                except Exception:
                    pass
                for selector in [
                    "img[src*='btn_inq'], img[src*='confirm'], img[src*='search']",
                    "button[type='submit'], input[type='submit']",
                    "a[onclick*='inq'], a[onclick*='search']",
                ]:
                    btns = driver.find_elements(By.CSS_SELECTOR, selector)
                    if btns:
                        try:
                            ActionChains(driver).move_to_element(btns[0]).click().perform()
                            time.sleep(5)
                            break
                        except Exception:
                            pass
                driver.switch_to.default_content()
                time.sleep(2)
            except Exception:
                driver.switch_to.default_content()
        dl_dir = os.path.join(os.path.dirname(__file__), "..", "downloads")
        os.makedirs(dl_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(dl_dir, f"taxbill_{ts}.png")
        try:
            driver.save_screenshot(screenshot_path)
            result["pdf_path"] = screenshot_path
        except Exception:
            pass
        page_text = ""
        try:
            page_text = driver.execute_script(
                "var texts=[];"
                "texts.push(document.body?document.body.innerText:'');"
                "return texts.join('\\n');"
            ) or ""
        except Exception:
            pass
        if not page_text.strip():
            all_frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
            for frm in all_frames:
                try:
                    driver.switch_to.frame(frm)
                    page_text += BeautifulSoup(driver.page_source, "html.parser").get_text() + "\n"
                    driver.switch_to.default_content()
                except Exception:
                    driver.switch_to.default_content()
        if not page_text.strip():
            page_text = BeautifulSoup(driver.page_source, "html.parser").get_text()
        buyer_biz2 = buyer_biz_clean
        biz_nos = re.findall(r"\d{3}-\d{2}-\d{5}", page_text)
        for bno in biz_nos:
            cleaned = bno.replace("-", "")
            if cleaned != buyer_biz2:
                result["supplier_biz_no"] = cleaned
                break
        if not result["supplier_biz_no"] and biz_nos:
            result["supplier_biz_no"] = biz_nos[0].replace("-", "")
        def find_amount(labels):
            for lbl in labels:
                m2 = re.search(lbl + r"[^\d]{0,15}([1-9][\d,]{2,})", page_text)
                if m2:
                    v = int(m2.group(1).replace(",", ""))
                    if v > 0:
                        return v
            return 0
        result["total_amount"]  = find_amount(["합계금액","청구금액","합 계","합계","총금액"])
        result["supply_amount"] = find_amount(["공급가액","공급금액"])
        result["tax_amount"]    = find_amount(["세액","부가세"])
        lines = [l.strip() for l in page_text.splitlines() if l.strip()]
        nlines = len(lines)
        def is_amount(s):
            return bool(re.match(r"^[1-9][\d,]+$", s))
        for i, l in enumerate(lines):
            if "상호(법인명)" in l or l == "상호":
                for j in range(i+1, min(i+5, nlines)):
                    if lines[j] and lines[j] not in ("성명","상호(법인명)","사업장주소","상호"):
                        result["supplier_name"] = lines[j]
                        break
                if result["supplier_name"]:
                    break
        if not result["supplier_name"]:
            for pattern in [r"공급자[\s\S]{0,10}상호[^가-힣\w]{0,5}([가-힣\w]{2,20})",
                            r"상호\s*[:\uff1a]?\s*([가-힣\w]{2,20})"]:
                m = re.search(pattern, page_text)
                if m:
                    result["supplier_name"] = m.group(1).strip()
                    break
        if not result["total_amount"]:
            for i, l in enumerate(lines):
                if l in ("합계금액","청구금액","합계"):
                    for j in range(i+1, min(i+15, nlines)):
                        if is_amount(lines[j]):
                            result["total_amount"] = int(lines[j].replace(",",""))
                            break
                    if result["total_amount"]:
                        break
        if not result["supply_amount"]:
            for i, l in enumerate(lines):
                if l == "단가":
                    amounts = [int(lines[j].replace(",","")) for j in range(i+1, min(i+20, nlines)) if is_amount(lines[j])]
                    if len(amounts) >= 2:
                        result["supply_amount"] = amounts[-2]
                        result["tax_amount"]    = amounts[-1]
                    break
        if not result["total_amount"] and result["supply_amount"]:
            result["total_amount"] = result["supply_amount"] + result["tax_amount"]
        if not result["supply_amount"] and result["total_amount"] and result["tax_amount"]:
            result["supply_amount"] = result["total_amount"] - result["tax_amount"]
        m = re.search(r"(\d{4})[\-./년]\s*(\d{1,2})[\-./월]\s*(\d{1,2})", page_text)
        if m:
            result["issue_date"] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        for i, l in enumerate(lines):
            if l in ("품목","품명"):
                for j in range(i+1, min(i+20, nlines)):
                    nm = lines[j]
                    if nm and not re.match(r"^[\d\s,]+$", nm) and nm not in ("규격","수량","단가","공급가액","세액","비고"):
                        result["item_name"] = nm[:30]
                        break
                break
        if not result["item_name"]:
            m = re.search(r"품목\s*[:\uff1a]?\s*([가-힣\w\s]{2,30})", page_text)
            if m:
                result["item_name"] = m.group(1).strip()[:30]
        try:
            if driver.current_window_handle != original_handle:
                driver.close()
                driver.switch_to.window(original_handle)
        except Exception:
            pass
    except Exception as e:
        result["error"] = str(e)
    return result

def run_pipeline(log_fn=None):
    def log(msg):
        if log_fn:
            log_fn(msg)
    base_url  = "https://www.bizmeka.com"
    buyer_biz = (get_setting("buyer_biz_no") or "").replace("-", "").replace(" ", "")
    max_count = int(get_setting("max_mail_count") or 200)
    driver    = _make_driver(headless=True)
    results   = []
    try:
        log("그룹웨어 로그인 중...")
        _selenium_login(driver, base_url)
        log("로그인 완료")
        log("메일 목록 조회 중...")
        mails = _get_mail_list_js(driver, base_url, keyword="", max_count=max_count)
        log(f"메일 {len(mails)}건 조회됨")
        vendors = get_vendors()
        existing = get_invoices()
        existing_keys = set()
        for inv in existing:
            existing_keys.add((inv.get("supplier_biz_no",""), inv.get("issue_date","")))
        for mail in mails:
            subject = mail.get("subject", "")
            href    = mail.get("href", "")
            date    = mail.get("date", "")
            log(f"메일 처리: {subject}")
            html_body = _get_mail_body_html(driver, base_url, href)
            mail_data = _parse_from_mail_body(html_body)
            taxbill_links = mail_data.get("taxbill_links", [])
            if not taxbill_links:
                log("  → 세금계산서 링크 없음, 스킵")
                continue
            log(f"  → 링크 {len(taxbill_links)}개: {taxbill_links[0][:60]}")
            page_data = _parse_taxbill_page_generic(driver, taxbill_links[0], buyer_biz)
            def merge(key):
                v = page_data.get(key)
                return v if v else mail_data.get(key, "" if isinstance(mail_data.get(key,""), str) else 0)
            invoice_data = {
                "supplier_biz_no": merge("supplier_biz_no"),
                "supplier_name":   merge("supplier_name"),
                "issue_date":      merge("issue_date") or date[:10],
                "supply_amount":   merge("supply_amount"),
                "tax_amount":      merge("tax_amount"),
                "total_amount":    merge("total_amount"),
                "item_name":       merge("item_name"),
                "pdf_path":        page_data.get("pdf_path",""),
                "mail_subject":    subject,
            }
            if page_data.get("error"):
                log(f"  → 파싱 오류: {page_data['error']}")
            key = (invoice_data["supplier_biz_no"], invoice_data["issue_date"])
            if key in existing_keys and key != ("",""):
                log(f"  → 중복 스킵")
                continue
            vendor = None
            if invoice_data["supplier_biz_no"]:
                for v in vendors:
                    if v.get("biz_no","").replace("-","") == invoice_data["supplier_biz_no"]:
                        vendor = v
                        break
            if not vendor and invoice_data["supplier_name"]:
                vendor = find_vendor_by_name(invoice_data["supplier_name"])
            if not vendor:
                log(f"  → 매입처 미등록: {invoice_data.get('supplier_name','')} ({invoice_data.get('supplier_biz_no','')})")
                continue
            log(f"  → 매입처 매칭: {vendor.get('name','')}")
            invoice_data["vendor_id"] = vendor.get("id","")
            inv_id = add_invoice(invoice_data)
            existing_keys.add(key)
            log(f"  → DB 저장 완료 (id={inv_id})")
            submitted = _submit_expense(driver, base_url, invoice_data, invoice_data.get("pdf_path"))
            status = "submitted" if submitted else "pending"
            update_invoice_status(inv_id, status)
            log(f"  → 지출결의서 {'제출' if submitted else '대기'} (id={inv_id})")
            results.append({**invoice_data, "id": inv_id, "status": status})
    except Exception as e:
        log(f"파이프라인 오류: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return results

def _submit_expense(driver, base_url, invoice_data, pdf_path=None):
    auto_submit = (get_setting("auto_submit") or "false").lower() == "true"
    company_id  = get_setting("bizmeka_company") or "obase"
    approver    = get_setting("approver_id") or ""
    cost_center = get_setting("cost_center") or ""
    driver.get(base_url + "/myoffice/appr/appr_write.aspx?compid=" + company_id + "&formcode=EXP001")
    time.sleep(4)
    def safe_fill(by, locator, value):
        try:
            el = driver.find_element(by, locator)
            el.clear()
            el.send_keys(str(value))
        except Exception:
            pass
    safe_fill(By.NAME, "title",       f"[세금계산서] {invoice_data.get('supplier_name','')} {invoice_data.get('issue_date','')}")
    safe_fill(By.NAME, "amount",      invoice_data.get("total_amount",0))
    safe_fill(By.NAME, "supply_amt",  invoice_data.get("supply_amount",0))
    safe_fill(By.NAME, "tax_amt",     invoice_data.get("tax_amount",0))
    safe_fill(By.NAME, "cost_center", cost_center)
    safe_fill(By.NAME, "remark",      f"공급자:{invoice_data.get('supplier_name','')} / 품목:{invoice_data.get('item_name','')} / 사업자:{invoice_data.get('supplier_biz_no','')}")
    if approver:
        safe_fill(By.NAME, "approver", approver)
    if pdf_path and os.path.exists(pdf_path):
        try:
            file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            file_input.send_keys(os.path.abspath(pdf_path))
            time.sleep(2)
        except Exception:
            pass
    if auto_submit:
        try:
            submit_btn = driver.find_element(By.CSS_SELECTOR,
                "input[type='submit'][value*='제출'], button[type='submit']")
            submit_btn.click()
            time.sleep(3)
            return True
        except Exception:
            return False
    return False
