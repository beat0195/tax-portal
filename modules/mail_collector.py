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
try:
    from webdriver_manager.chrome import ChromeDriverManager
    _USE_WDM = True
except ImportError:
    _USE_WDM = False

FOLDER_ID = "AAMkAGUyNWIyYmU4LTBjM2MtNGM4OS04YTE4LWFhZjQ4ZTY3ZmE4ZAAuAAAAAACB7Z4ydzgUQo6MOiLN9ceFAQD2vFdoTp31Tb13wR9oUYV6AAAABH/bAAA="


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
        sender = (resp.find("sender") or type("", (), {"text": ""})()).text
        mails.append({
            "id": href,
            "subject": subject,
            "sender": sender,
            "date": date,
        })
    return mails


def _get_mail_body_url(base_url, mail_id):
    import urllib.parse
    return (base_url + "/myoffice/ezEmail/mail_read_Cross.aspx?URL="
            + urllib.parse.quote(mail_id))


def _extract_taxbill_link(driver, mail_url):
    try:
        driver.get(mail_url)
        time.sleep(3)
        # 방법1: JS로 모든 frame 포함 전체 href 추출
        all_hrefs = driver.execute_script(
            "var hrefs=[];"
            "function getLinks(doc){"
            "  var tags=doc.querySelectorAll('a[href]');"
            "  for(var i=0;i<tags.length;i++){hrefs.push(tags[i].href);}"
            "}"
            "try{getLinks(document);}catch(e){}"
            "for(var i=0;i<window.frames.length;i++){"
            "  try{getLinks(window.frames[i].document);}catch(e){}"
            "}"
            "return hrefs;"
        ) or []
        for href in all_hrefs:
            if href and ("taxbill" in href.lower() or "etax" in href.lower() or "hot_gate" in href.lower()):
                return href
        # 방법2: Selenium frame switch
        frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
        for frm in frames:
            try:
                driver.switch_to.frame(frm)
                soup2 = BeautifulSoup(driver.page_source, "html.parser")
                link = _find_taxbill_link_in_soup(soup2)
                driver.switch_to.default_content()
                if link:
                    return link
            except Exception:
                driver.switch_to.default_content()
        # 방법3: page_source 직접 파싱
        soup = BeautifulSoup(driver.page_source, "html.parser")
        return _find_taxbill_link_in_soup(soup)
    except Exception:
        return None

def _find_taxbill_link_in_soup(soup):
    keywords = ["사용자확인", "바로가기", "세금계산서확인", "확인하기"]
    for tag in soup.find_all(["a", "button"]):
        text = tag.get_text(strip=True)
        href = tag.get("href", "")
        onclick = tag.get("onclick", "")
        if any(k in text for k in keywords):
            if href and href.startswith("http"):
                return href
            m = re.search(r"https?://[^\s'\"]+", onclick)
            if m:
                return m.group()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if "taxbill" in href.lower() or "etax" in href.lower():
            return href
    return None


def _parse_taxbill_page(driver, taxbill_url):
    result = {
        "supplier_name": "", "supplier_biz_no": "",
        "issue_date": "", "supply_amount": 0,
        "tax_amount": 0, "total_amount": 0,
        "item_name": "", "pdf_path": "",
    }
    try:
        driver.get(taxbill_url)
        time.sleep(4)
        # -- 1) 스크린샷 저장 (페이지 로드 직후)
        dl_dir = os.path.join(os.path.dirname(__file__), "..", "downloads")
        os.makedirs(dl_dir, exist_ok=True)
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(dl_dir, f"taxbill_{ts}.png")
        try:
            driver.save_screenshot(screenshot_path)
            result["pdf_path"] = screenshot_path
        except Exception:
            pass
        # -- 2) frame/iframe 내부 텍스트 추출 (여러 방법 시도)
        page_text = ""
        # 방법A: 모든 frame/iframe 텍스트 합치기
        try:
            page_text = driver.execute_script(
                "var texts=[];"
                "try{texts.push(document.body.innerText);}catch(e){}"
                "for(var i=0;i<window.frames.length;i++){"
                "  try{texts.push(window.frames[i].document.body.innerText);}catch(e){}"
                "}"
                "return texts.join('\n');"
            ) or ""
        except Exception:
            pass
        # 방법B: Selenium frame switch
        if not page_text.strip():
            try:
                frames = driver.find_elements(By.TAG_NAME, "frame") +                          driver.find_elements(By.TAG_NAME, "iframe")
                for frm in frames:
                    try:
                        driver.switch_to.frame(frm)
                        page_text += driver.execute_script(
                            "return document.body ? document.body.innerText : '';") or ""
                        driver.switch_to.default_content()
                    except Exception:
                        driver.switch_to.default_content()
            except Exception:
                pass
        # 방법C: BeautifulSoup fallback
        if not page_text.strip():
            page_text = BeautifulSoup(driver.page_source, "html.parser").get_text()
        # -- 3) 사업자번호 파싱 (XXX-XX-XXXXX 형식)
        biz_nos = re.findall(r"\d{3}-\d{2}-\d{5}", page_text)
        buyer_biz = (get_setting("buyer_biz_no") or "").replace("-", "")
        for bno in biz_nos:
            cleaned = bno.replace("-", "")
            if cleaned != buyer_biz:
                result["supplier_biz_no"] = cleaned
                break
        if not result["supplier_biz_no"] and biz_nos:
            result["supplier_biz_no"] = biz_nos[0].replace("-", "")
        # -- 4) 금액 파싱
        for label, key in [("공급가액", "supply_amount"),
                            ("세액", "tax_amount"),
                            ("합계금액", "total_amount"),
                            ("합 계", "total_amount"),
                            ("합계", "total_amount")]:
            m2 = re.search(label + r"[^\d]{0,10}([\d,]{4,})", page_text)
            if m2:
                val = int(m2.group(1).replace(",", ""))
                if val > 0:
                    result[key] = val
        if not result["total_amount"] and result["supply_amount"]:
            result["total_amount"] = result["supply_amount"] + result["tax_amount"]
        # -- 5) 발행일자
        m = re.search(r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})", page_text)
        if m:
            result["issue_date"] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        # -- 6) 공급자 상호
        m = re.search(r"상\s*호[^\w가-힣]*([^\n\r\t,]{2,20})", page_text)
        if m:
            result["supplier_name"] = m.group(1).strip()
        # -- 7) 품목
        m = re.search(r"품\s*목[^\w가-힣]*([^\n\r\t,]{2,30})", page_text)
        if m:
            result["item_name"] = m.group(1).strip()
    except Exception as e:
        result["error"] = str(e)
    return result


def _submit_expense(driver, base_url, invoice_data, pdf_path=None):
    auto_submit = (get_setting("auto_submit") or "false").lower() == "true"
    company_id = get_setting("bizmeka_company") or "obase"
    expense_url = (
        base_url + "/myoffice/ezApproval/approval_write.aspx"
        "?compid=" + company_id + "&doctype=expenditure"
    )
    try:
        driver.get(expense_url)
        time.sleep(3)
        title = (f"[지출결의] {invoice_data.get('supplier_name','')}"
                 f" {invoice_data.get('issue_date','')}")
        for sel in ["input[id*='title']", "input[name*='title']",
                    "input[id*='subject']", "input[name*='subject']"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                els[0].clear(); els[0].send_keys(title); break
        amount = invoice_data.get("total_amount", 0)
        for sel in ["input[id*='amount']", "input[name*='amount']",
                    "input[id*='money']", "input[name*='money']"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                els[0].clear(); els[0].send_keys(str(amount)); break
        content = (
            f"공급자: {invoice_data.get('supplier_name','')}\n"
            f"사업자번호: {invoice_data.get('supplier_biz_no','')}\n"
            f"공급가액: {invoice_data.get('supply_amount',0):,}원\n"
            f"세액: {invoice_data.get('tax_amount',0):,}원\n"
            f"합계: {invoice_data.get('total_amount',0):,}원\n"
            f"품목: {invoice_data.get('item_name','')}"
        )
        for sel in ["textarea", "div[contenteditable='true']"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                try:
                    els[0].clear(); els[0].send_keys(content)
                except Exception:
                    driver.execute_script(
                        "arguments[0].innerText=arguments[1]", els[0], content)
                break
        if pdf_path and os.path.exists(pdf_path):
            for el in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
                try:
                    el.send_keys(os.path.abspath(pdf_path))
                    time.sleep(2)
                    break
                except Exception:
                    continue
        if auto_submit:
            for sel in ["input[value*='상신']", "a[onclick*='submit']",
                        "button[id*='submit']", "button[title*='상신']"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    els[0].click(); time.sleep(2)
                    return True, "지출결의서 상신 완료"
            return False, "상신 버튼을 찾지 못했습니다."
        else:
            for sel in ["input[value*='임시저장']", "a[onclick*='save']",
                        "button[id*='save']", "button[title*='임시저장']"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    els[0].click(); time.sleep(2)
                    return True, "지출결의서 임시저장 완료"
            return True, "지출결의서 작성 완료 (수동 저장 필요)"
    except Exception as e:
        return False, f"지출결의서 오류: {e}"


def run_full_pipeline():
    result = {
        "new": 0, "matched": 0, "submitted": 0,
        "skipped": 0, "error": 0, "error_msg": ""
    }
    base_url = "https://ngwx.ktbizoffice.com"
    driver = None
    try:
        driver = _make_driver(headless=True)
        _selenium_login(driver, base_url)
        keyword = get_setting("mail_keyword") or "세금계산서"
        mails = _get_mail_list_js(driver, base_url, keyword=keyword, max_count=200)
        if not mails:
            result["error_msg"] = "세금계산서 메일 없음 (키워드: " + keyword + ")"
            return result
        existing = get_invoices()
        done_subjects = {inv["mail_subject"] for inv in existing}
        for mail in mails:
            subject = mail.get("subject", "")
            date = mail.get("date", "")[:10]
            sender = mail.get("sender", "")
            mail_id = mail.get("id", "")
            if not mail_id or subject in done_subjects:
                result["skipped"] += 1
                continue
            vendor = None
            biz_no = ""
            clean_sub = subject.replace("(주)", "").replace(" ", "")
            for v in get_vendors():
                clean_nm = v["name"].replace("(주)", "").replace(" ", "")
                if clean_nm and clean_nm in clean_sub:
                    vendor = v
                    biz_no = v["biz_number"]
                    break
            if not vendor and sender:
                vendor = find_vendor_by_name(sender)
            status = "MATCHED" if vendor else "PENDING"
            memo = (f"매입처 매칭: {vendor['name']}" if vendor
                    else "매입처 미등록 – 확인 필요")
            invoice_data = {
                "mail_subject": subject,
                "mail_date": date,
                "issue_date": date,
                "supplier_name": vendor["name"] if vendor else sender,
                "supplier_biz_no": biz_no,
                "supply_amount": 0,
                "tax_amount": 0,
                "total_amount": 0,
                "item_name": "",
                "status": status,
                "result_memo": memo,
            }
            if vendor:
                mail_url = _get_mail_body_url(base_url, mail_id)
                taxbill_url = _extract_taxbill_link(driver, mail_url)
                if taxbill_url:
                    tb = _parse_taxbill_page(driver, taxbill_url)
                    invoice_data.update({
                        "issue_date": tb.get("issue_date") or date,
                        "supplier_name": tb.get("supplier_name") or invoice_data["supplier_name"],
                        "supplier_biz_no": tb.get("supplier_biz_no") or biz_no,
                        "supply_amount": tb.get("supply_amount", 0),
                        "tax_amount": tb.get("tax_amount", 0),
                        "total_amount": tb.get("total_amount", 0),
                        "item_name": tb.get("item_name", ""),
                    })
                    pdf_path = tb.get("pdf_path", "")
                    ok, msg = _submit_expense(driver, base_url, invoice_data, pdf_path)
                    if ok:
                        result["submitted"] += 1
                        invoice_data["status"] = "SUBMITTED"
                        invoice_data["result_memo"] = msg
                    else:
                        invoice_data["result_memo"] = msg
            add_invoice(invoice_data)
            result["new"] += 1
            if vendor:
                result["matched"] += 1
            done_subjects.add(subject)
    except Exception as e:
        result["error"] += 1
        result["error_msg"] = str(e)
    finally:
        if driver:
            driver.quit()
    return result


def retry_invoice(invoice_id):
    invoices = get_invoices()
    target = next((i for i in invoices if i["id"] == invoice_id), None)
    if not target:
        return False, "이력을 찾을 수 없습니다."
    base_url = "https://ngwx.ktbizoffice.com"
    driver = None
    try:
        driver = _make_driver(headless=True)
        _selenium_login(driver, base_url)
        ok, msg = _submit_expense(driver, base_url, dict(target))
        if ok:
            update_invoice_status(invoice_id, "SUBMITTED", msg)
        return ok, msg
    except Exception as e:
        return False, str(e)
    finally:
        if driver:
            driver.quit()
