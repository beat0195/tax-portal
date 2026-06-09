import sys, os, base64, warnings, re, time
import requests
from bs4 import BeautifulSoup
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from database import (get_setting, add_invoice, get_invoices,
                      find_vendor_by_biz_no, get_vendors,
                      find_vendor_by_name, update_invoice_status)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
try:
    from webdriver_manager.chrome import ChromeDriverManager
    _USE_WDM = True
except ImportError:
    _USE_WDM = False


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


def _login_groupware():
    base_url   = "https://ngwx.ktbizoffice.com"
    company_id = get_setting("bizmeka_company") or "obase"
    login_page = f"{base_url}/LoginN.aspx?compid={company_id}"
    user_id    = get_setting("groupware_id") or ""
    pw         = get_setting("groupware_pw") or ""

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    resp = session.get(login_page, verify=False, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")

    def val(name):
        tag = soup.find("input", {"name": name})
        return tag["value"] if tag else ""

    modulus  = val("publicModulus")
    exponent = val("publicExponent")
    if not modulus:
        raise Exception("RSA 공개키를 가져오지 못했습니다.")

    enc_id = _rsa_encrypt(modulus, exponent, user_id)
    enc_pw = _rsa_encrypt(modulus, exponent, pw)

    payload = {
        "__VIEWSTATE": val("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": val("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION": val("__EVENTVALIDATION"),
        "TextUserID": "", "TextPassword": "",
        "EncryptUserID": enc_id, "EncryptPassword": enc_pw,
        "Encryptcid": company_id, "seq": "", "pageNum": "", "sel_part": "",
        "LoginButton.x": "0", "LoginButton.y": "0",
    }
    login_resp = session.post(login_page, data=payload,
                              verify=False, timeout=15, allow_redirects=True)
    if "LoginN.aspx" in login_resp.url:
        raise Exception("그룹웨어 로그인 실패")
    return session, base_url


def _get_inbox_folder_id(session, base_url):
    fixed_id = "AAMkAGUyNWIyYmU4LTBjM2MtNGM4OS04YTE4LWFhZjQ4ZTY3ZmE4ZAAuAAAAAAACB7Z4ydzgUQo6MOiLN9ceFAQD2vFdoTp31Tb13wR9oUYV6AAAABH/bAAA="
    saved = get_setting("groupware_inbox_id")
    return saved if saved else fixed_id


def _get_mail_list(session, base_url, folder_id,
                   keyword="세금계산서", max_count=50):
    url = f"{base_url}/myoffice/ezEmail/remote/mail_get_list_cross.aspx"
    xml_data = (
        f"<DATA>"
        f"<FOLDERID>{folder_id}</FOLDERID>"
        f'<SORTTYPE> ORDER BY "urn:schemas:httpmail:datereceived" DESC</SORTTYPE>'
        f"<SEARCH>SUBJECT={keyword}</SEARCH>"
        f"<START>0</START><END>{max_count - 1}</END>"
        f"<VIEWSELECTINDEX>0</VIEWSELECTINDEX>"
        f"</DATA>"
    )
    resp = session.post(
        url, data=xml_data.encode("utf-8"), verify=False, timeout=15,
        headers={"Content-Type": "text/xml; charset=utf-8"})
    return resp.text


def _parse_mail_list(xml_text):
    soup = BeautifulSoup(xml_text, "xml")
    mails = []
    for item in soup.find_all("item"):
        mails.append({
            "id":      (item.find("MAILID") or item.find("mailid") or type("", (), {"text": ""})()).text,
            "subject": (item.find("SUBJECT") or type("", (), {"text": ""})()).text,
            "sender":  (item.find("SENDERNAME") or type("", (), {"text": ""})()).text,
            "date":    (item.find("DATERECEIVED") or type("", (), {"text": ""})()).text,
        })
    return mails


def _get_mail_body_url(session, base_url, mail_id, folder_id):
    company_id = get_setting("bizmeka_company") or "obase"
    return (
        f"{base_url}/myoffice/ezEmail/mail_read_Cross.aspx"
        f"?compid={company_id}&mailid={mail_id}&folderid={folder_id}"
    )
def _extract_taxbill_link(session, mail_url):
    """메일 본문에서 '사용자확인 바로가기' 링크 추출"""
    try:
        resp = session.get(mail_url, verify=False, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # iframe이 있으면 본문 iframe 로드
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src", "")
            if not src:
                continue
            if not src.startswith("http"):
                src = "https://ngwx.ktbizoffice.com" + src
            try:
                resp2 = session.get(src, verify=False, timeout=15)
                soup2 = BeautifulSoup(resp2.text, "html.parser")
                # 이 iframe에서 링크 탐색
                link = _find_taxbill_link_in_soup(soup2)
                if link:
                    return link
            except Exception:
                continue

        # iframe 없으면 본문 직접 탐색
        return _find_taxbill_link_in_soup(soup)
    except Exception:
        return None


def _find_taxbill_link_in_soup(soup):
    """soup에서 세금계산서 링크 찾기"""
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
    # taxbill365 링크 직접 탐색
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if "taxbill" in href.lower() or "etax" in href.lower():
            return href
    return None


def _parse_taxbill_page(driver, taxbill_url):
    """Selenium으로 세금계산서 페이지 열어서 데이터 파싱"""
    result = {
        "supplier_name": "", "supplier_biz_no": "",
        "issue_date": "", "supply_amount": 0,
        "tax_amount": 0, "total_amount": 0,
        "item_name": "", "pdf_path": "",
    }
    try:
        driver.get(taxbill_url)
        time.sleep(3)

        # 사업자번호 입력 폼 처리
        buyer_biz = get_setting("buyer_biz_no") or ""
        biz_inputs = driver.find_elements(By.CSS_SELECTOR,
            "input[name*='biz'], input[id*='biz'], "
            "input[placeholder*='사업자'], input[placeholder*='조회']")
        if biz_inputs and buyer_biz:
            biz_inputs[0].clear()
            biz_inputs[0].send_keys(buyer_biz.replace("-", ""))
            btns = driver.find_elements(By.CSS_SELECTOR,
                "button[type='submit'], input[type='submit'], "
                "a[onclick*='search'], button[onclick*='view']")
            if btns:
                btns[0].click()
                time.sleep(2)

        page_text = BeautifulSoup(driver.page_source, "html.parser").get_text()

        # 공급자 사업자번호
        m = re.search(r'\d{3}-\d{2}-\d{5}', page_text)
        if m:
            result["supplier_biz_no"] = m.group().replace("-", "")

        # 공급가액 / 세액 / 합계
        for label, key in [("공급가액", "supply_amount"),
                           ("세액", "tax_amount"),
                           ("합계금액", "total_amount"),
                           ("합 계", "total_amount"),
                           ("합계", "total_amount")]:
            m = re.search(label + r'[^\d]*([\d,]+)', page_text)
            if m:
                result[key] = int(m.group(1).replace(",", ""))

        if not result["total_amount"] and result["supply_amount"]:
            result["total_amount"] = result["supply_amount"] + result["tax_amount"]

        # 발행일
        m = re.search(r'(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})', page_text)
        if m:
            result["issue_date"] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

        # 공급자명
        m = re.search(r'상\s*호[^\w가-힣]*([^\n\r\t,]{2,20})', page_text)
        if m:
            result["supplier_name"] = m.group(1).strip()

        # 품목
        m = re.search(r'품\s*목[^\w가-힣]*([^\n\r\t,]{2,30})', page_text)
        if m:
            result["item_name"] = m.group(1).strip()

        # PDF 저장 시도
        dl_dir = os.path.join(os.path.dirname(__file__), "..", "downloads")
        os.makedirs(dl_dir, exist_ok=True)
        for btn in driver.find_elements(By.CSS_SELECTOR,
                "a[href*='.pdf'], button[onclick*='pdf'], a[onclick*='pdf'], "
                "input[value*='PDF'], a[title*='인쇄'], button[title*='인쇄']"):
            try:
                btn.click()
                time.sleep(3)
                files = sorted(
                    [os.path.join(dl_dir, f) for f in os.listdir(dl_dir)],
                    key=os.path.getmtime, reverse=True)
                if files:
                    result["pdf_path"] = files[0]
                break
            except Exception:
                continue

    except Exception as e:
        result["error"] = str(e)
    return result


def _submit_expense(driver, base_url, invoice_data, pdf_path=None):
    """비즈메카 지출결의서 자동 작성"""
    auto_submit = (get_setting("auto_submit") or "false").lower() == "true"
    company_id  = get_setting("bizmeka_company") or "obase"

    # 지출결의서 작성 URL (비즈메카 그룹웨어)
    expense_url = (
        f"{base_url}/myoffice/ezApproval/approval_write.aspx"
        f"?compid={company_id}&doctype=expenditure"
    )
    try:
        driver.get(expense_url)
        wait = WebDriverWait(driver, 15)
        time.sleep(3)

        title = (f"[지출결의] {invoice_data.get('supplier_name','')}"
                 f" {invoice_data.get('issue_date','')}")

        # 제목
        for sel in ["input[id*='title']", "input[name*='title']",
                    "input[id*='subject']", "input[name*='subject']"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                els[0].clear(); els[0].send_keys(title); break

        # 금액
        amount = invoice_data.get("total_amount", 0)
        for sel in ["input[id*='amount']", "input[name*='amount']",
                    "input[id*='money']", "input[name*='money']"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                els[0].clear(); els[0].send_keys(str(amount)); break

        # 내용/적요
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

        # 파일 첨부
        if pdf_path and os.path.exists(pdf_path):
            for el in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
                try:
                    el.send_keys(os.path.abspath(pdf_path))
                    time.sleep(2)
                    break
                except Exception:
                    continue

        # 상신 or 임시저장
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


def _selenium_login(driver, base_url):
    """Selenium으로 그룹웨어 로그인"""
    company_id = get_setting("bizmeka_company") or "obase"
    user_id    = get_setting("groupware_id") or ""
    pw         = get_setting("groupware_pw") or ""
    driver.get(f"{base_url}/LoginN.aspx?compid={company_id}")
    time.sleep(2)
    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        def val(name):
            t = soup.find("input", {"name": name})
            return t["value"] if t else ""
        mod = val("publicModulus"); exp = val("publicExponent")
        if mod:
            ei = _rsa_encrypt(mod, exp, user_id)
            ep = _rsa_encrypt(mod, exp, pw)
            driver.execute_script(
                f"document.querySelector('[name=EncryptUserID]').value='{ei}';"
                f"document.querySelector('[name=EncryptPassword]').value='{ep}';"
                f"document.querySelector('[name=Encryptcid]').value='{company_id}';")
            btns = driver.find_elements(By.NAME, "LoginButton")
            if btns:
                btns[0].click()
            else:
                driver.execute_script(
                    "document.querySelector('input[name*=Login]').click()")
            time.sleep(3)
    except Exception:
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "TextUserID")))
            driver.find_element(By.ID, "TextUserID").send_keys(user_id)
            driver.find_element(By.ID, "TextPassword").send_keys(pw)
            driver.find_element(By.ID, "LoginButton").click()
            time.sleep(3)
        except Exception:
            pass


# ────────────────────────────────────────────────────────
#  메인 파이프라인
# ────────────────────────────────────────────────────────
def run_full_pipeline():
    result = {
        "new": 0, "matched": 0, "submitted": 0,
        "skipped": 0, "error": 0, "error_msg": ""
    }

    # 1. requests 로그인
    try:
        session, base_url = _login_groupware()
    except Exception as e:
        result["error"] += 1
        result["error_msg"] = f"로그인 실패: {e}"
        return result

    # 2. 메일 목록
    try:
        folder_id = _get_inbox_folder_id(session, base_url)
        keyword   = get_setting("mail_keyword") or "세금계산서"
        xml_text  = _get_mail_list(session, base_url, folder_id, keyword=keyword)
        mails     = _parse_mail_list(xml_text)
    except Exception as e:
        result["error"] += 1
        result["error_msg"] = f"메일 목록 실패: {e}"
        return result

    if not mails:
        return result

    # 3. 기존 처리 목록 (중복 방지)
    existing = get_invoices()
    done_subjects = {inv["mail_subject"] for inv in existing}

    driver = None
    try:
        for mail in mails:
            subject = mail.get("subject", "")
            date    = mail.get("date", "")[:10]
            sender  = mail.get("sender", "")
            mail_id = mail.get("id", "")

            if not mail_id or subject in done_subjects:
                result["skipped"] += 1
                continue

            # 매입처 매칭
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
            memo   = (f"매입처 매칭: {vendor['name']}" if vendor
                      else "매입처 미등록 – 확인 필요")

            invoice_data = {
                "mail_subject":    subject,
                "mail_date":       date,
                "issue_date":      date,
                "supplier_name":   vendor["name"] if vendor else sender,
                "supplier_biz_no": biz_no,
                "supply_amount":   0,
                "tax_amount":      0,
                "total_amount":    0,
                "item_name":       "",
                "status":          status,
                "result_memo":     memo,
            }

            # 세금계산서 링크 추출 및 파싱
            if vendor:
                mail_url    = _get_mail_body_url(session, base_url, mail_id, folder_id)
                taxbill_url = _extract_taxbill_link(session, mail_url)

                if taxbill_url:
                    if driver is None:
                        driver = _make_driver(headless=True)
                        _selenium_login(driver, base_url)

                    tb = _parse_taxbill_page(driver, taxbill_url)
                    invoice_data.update({
                        "issue_date":      tb.get("issue_date") or date,
                        "supplier_name":   tb.get("supplier_name") or invoice_data["supplier_name"],
                        "supplier_biz_no": tb.get("supplier_biz_no") or biz_no,
                        "supply_amount":   tb.get("supply_amount", 0),
                        "tax_amount":      tb.get("tax_amount", 0),
                        "total_amount":    tb.get("total_amount", 0),
                        "item_name":       tb.get("item_name", ""),
                    })

                    pdf_path = tb.get("pdf_path", "")
                    ok, msg  = _submit_expense(driver, base_url, invoice_data, pdf_path)
                    if ok:
                        result["submitted"] += 1
                        invoice_data["status"]      = "SUBMITTED"
                        invoice_data["result_memo"] = msg
                    else:
                        invoice_data["result_memo"] = msg

            add_invoice(invoice_data)
            result["new"] += 1
            if vendor:
                result["matched"] += 1
            done_subjects.add(subject)

    except Exception as e:
        result["error"]    += 1
        result["error_msg"] = str(e)
    finally:
        if driver:
            driver.quit()

    return result


def retry_invoice(invoice_id):
    """특정 건 재처리"""
    invoices = get_invoices()
    target = next((i for i in invoices if i["id"] == invoice_id), None)
    if not target:
        return False, "이력을 찾을 수 없습니다."
    driver = None
    try:
        session, base_url = _login_groupware()
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