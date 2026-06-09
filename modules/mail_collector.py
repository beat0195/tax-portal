import sys, os, base64, warnings, re
import requests
from bs4 import BeautifulSoup
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from database import get_setting, add_invoice, get_invoices, find_vendor_by_biz_no, get_vendors, find_vendor_by_name


def _rsa_encrypt(modulus_hex, exponent_hex, plaintext):
    n = int(modulus_hex, 16)
    e = int(exponent_hex, 16)
    key = RSA.construct((n, e))
    cipher = PKCS1_v1_5.new(key)
    b64_text = base64.b64encode(plaintext.encode("utf-8"))
    return cipher.encrypt(b64_text).hex()


def _login_groupware():
    base_url   = "https://ngwx.ktbizoffice.com"
    company_id = get_setting("bizmeka_company") or "obase"
    login_page = f"{base_url}/LoginN.aspx?compid={company_id}"
    user_id    = get_setting("groupware_id") or ""
    pw         = get_setting("groupware_pw")  or ""

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    resp = session.get(login_page, verify=False, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")

    def val(name):
        tag = soup.find("input", {"name": name})
        return tag["value"] if tag else ""

    modulus  = val("publicModulus")
    exponent = val("publicExponent")
    enc_id   = _rsa_encrypt(modulus, exponent, user_id)
    enc_pw   = _rsa_encrypt(modulus, exponent, pw)

    payload = {
        "__VIEWSTATE":          val("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": val("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION":    val("__EVENTVALIDATION"),
        "TextUserID": "", "TextPassword": "",
        "EncryptUserID": enc_id, "EncryptPassword": enc_pw,
        "Encryptcid": company_id,
        "seq": "", "pageNum": "", "sel_part": "",
        "LoginButton.x": "0", "LoginButton.y": "0",
    }
    login_resp = session.post(login_page, data=payload, verify=False, timeout=15, allow_redirects=True)
    if "LoginN.aspx" in login_resp.url:
        raise Exception("그룹웨어 로그인 실패")
    return session, base_url


def _get_inbox_folder_id(session, base_url):
    fixed_id = "AAMkAGUyNWIyYmU4LTBjM2MtNGM4OS04YTE4LWFhZjQ4ZTY3ZmE4ZAAuAAAAAACB7Z4ydzgUQo6MOiLN9ceFAQD2vFdoTp31Tb13wR9oUYV6AAAABH/bAAA="
    saved = get_setting("groupware_inbox_id")
    return saved if saved else fixed_id


def _get_mail_list(session, base_url, folder_id, keyword="세금계산서", max_count=50):
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
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "Referer": f"{base_url}/myoffice/ezEmail/mail_list_Cross.aspx?Subfunction=1",
        }
    )
    return resp.text


def _parse_mail_list(xml_text):
    """KT 비즈오피스 maillist XML 파싱 (response 태그 기반)"""
    mails = []
    try:
        soup = BeautifulSoup(xml_text, "html.parser")
        for item in soup.find_all("response"):
            def g(tag_name):
                tag = item.find(tag_name)
                return tag.get_text(strip=True) if tag else ""
            subject  = g("subject")
            sender   = g("sender")
            date_str = g("receivedt")
            href     = g("href")
            attach   = g("attach")
            if subject:
                mails.append({
                    "subject": subject,
                    "sender":  sender,
                    "date":    date_str,
                    "href":    href,
                    "attach":  attach == "1",
                })
    except Exception:
        pass
    return mails


def _extract_biz_no(text):
    for p in [r"\d{3}-\d{2}-\d{5}", r"\d{10}"]:
        m = re.search(p, text)
        if m:
            return m.group().replace("-", "")
    return ""


def _test_groupware_bizmeka(target):
    base_url   = "https://ngwx.ktbizoffice.com"
    company_id = get_setting("bizmeka_company") or "obase"
    login_page = f"{base_url}/LoginN.aspx?compid={company_id}"
    user_id = get_setting("bizmeka_id" if target == "bizmeka" else "groupware_id") or ""
    pw      = get_setting("bizmeka_pw"  if target == "bizmeka" else "groupware_pw")  or ""
    label   = "비즈메카" if target == "bizmeka" else "그룹웨어"

    if not user_id or not pw:
        return False, f"{label} ID 또는 비밀번호가 설정되지 않았습니다."
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        resp = session.get(login_page, verify=False, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        def val(name):
            tag = soup.find("input", {"name": name})
            return tag["value"] if tag else ""
        modulus  = val("publicModulus")
        exponent = val("publicExponent")
        if not modulus:
            return False, "RSA 공개키를 가져오지 못했습니다."
        enc_id = _rsa_encrypt(modulus, exponent, user_id)
        enc_pw = _rsa_encrypt(modulus, exponent, pw)
        payload = {
            "__VIEWSTATE": val("__VIEWSTATE"), "__VIEWSTATEGENERATOR": val("__VIEWSTATEGENERATOR"),
            "__EVENTVALIDATION": val("__EVENTVALIDATION"),
            "TextUserID": "", "TextPassword": "",
            "EncryptUserID": enc_id, "EncryptPassword": enc_pw,
            "Encryptcid": company_id, "seq": "", "pageNum": "", "sel_part": "",
            "LoginButton.x": "0", "LoginButton.y": "0",
        }
        r = session.post(login_page, data=payload, verify=False, timeout=15, allow_redirects=True)
        if "LoginN.aspx" in r.url or "login" in r.url.lower():
            return False, f"로그인 실패"
        return True, f"{label} 로그인 성공 (ID: {user_id})"
    except Exception as e:
        return False, f"오류: {str(e)}"


def test_connection(target: str):
    if target in ("bizmeka", "groupware"):
        return _test_groupware_bizmeka(target)
    return False, f"알 수 없는 대상: {target}"


def run_full_pipeline():
    """메일 수집 → 파싱 → 매입처 매칭 → DB 저장"""
    result = {"new": 0, "matched": 0, "skipped": 0, "error": 0}
    try:
        session, base_url = _login_groupware()
        folder_id = _get_inbox_folder_id(session, base_url)
        keyword   = get_setting("mail_keyword") or "세금계산서"
        xml_text  = _get_mail_list(session, base_url, folder_id, keyword=keyword)

        debug_path = os.path.join(os.path.dirname(__file__), "..", "last_mail_result.xml")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(xml_text)

        mails = _parse_mail_list(xml_text)
        existing = {inv["mail_subject"] for inv in get_invoices(limit=500)}

        for mail in mails:
            subject = mail.get("subject", "")
            sender  = mail.get("sender", "")
            date    = mail.get("date", "")

            if subject in existing:
                result["skipped"] += 1
                continue

            biz_no = _extract_biz_no(subject + " " + sender)
            vendor = find_vendor_by_biz_no(biz_no) if biz_no else None
            if not vendor:
                clean_subject = subject.replace("(주)","").replace(" ","")
                for v in get_vendors():
                    clean_name = v["name"].replace("(주)","").replace(" ","")
                    if clean_name and clean_name in clean_subject:
                        vendor = v
                        biz_no = v["biz_number"]
                        break
            if not vendor:
                vendor = find_vendor_by_name(sender_name) if sender_name else None
            status = "MATCHED" if vendor else "PENDING"
            memo   = f"매입처 매칭: {vendor['name']}" if vendor else "매입처 미등록 - 확인 필요"

            if vendor:
                result["matched"] += 1

            add_invoice({
                "mail_subject":    subject,
                "mail_date":       date,
                "supplier_name":   vendor["name"] if vendor else sender,
                "supplier_biz_no": biz_no,
                "status":          status,
                "result_memo":     memo,
            })
            result["new"] += 1

        return result
    except Exception as e:
        result["error"] += 1
        result["error_msg"] = str(e)
        return result




