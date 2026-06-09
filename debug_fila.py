import sys, time, requests
sys.path.insert(0, '.')
from modules.mail_collector import _make_driver, _selenium_login, _get_mail_list_js, _get_mail_body_url, _extract_taxbill_link
from bs4 import BeautifulSoup

TAXBILL_URL = "https://home.taxbill365.com/jsp/hot_gate.jsp?TARGET_URL=/jsp/main/main_0013_00.jsp&ISSU_ID=32E71049941F061A3075BA0C1CDEAF1DDB26B0437E67318E&SEQ_NO=2026052941000026zzzreov0_149713956535295956_1&CORP_TYPE=BUYR"

driver = _make_driver(headless=True)
try:
    _selenium_login(driver, 'https://ngwx.ktbizoffice.com')
    print("비즈메카 로그인 완료")

    # 방법1: requests로 비즈메카 쿠키 가지고 taxbill365 접근
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"])

    resp = session.get(TAXBILL_URL, allow_redirects=True, timeout=15)
    print("requests 상태:", resp.status_code, "최종URL:", resp.url)
    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text()
    print("requests 텍스트 (500자):", text[:500])

    # 방법2: Selenium - 비즈메카 쿠키를 taxbill365에 추가하고 접근
    print()
    print("Selenium 시도...")
    driver.get("https://home.taxbill365.com")
    time.sleep(2)
    # 비즈메카 쿠키 주입
    for cookie in driver.get_cookies():
        try:
            driver.add_cookie({"name": cookie["name"], "value": cookie["value"]})
        except Exception:
            pass
    driver.get(TAXBILL_URL)
    time.sleep(5)
    print("Selenium 현재 URL:", driver.current_url)

    text2 = driver.execute_script("return document.body ? document.body.innerText : '';") or ""
    print("Selenium 텍스트 (500자):", text2[:500])

    driver.save_screenshot("downloads/taxbill_debug.png")
    print("스크린샷 저장 완료")
finally:
    driver.quit()
