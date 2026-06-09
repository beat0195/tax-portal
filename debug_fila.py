import sys, time
sys.path.insert(0, '.')
from modules.mail_collector import _make_driver, _selenium_login, _get_mail_list_js, _get_mail_body_url, _extract_taxbill_link
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

TAXBILL_URL = "https://home.taxbill365.com/jsp/hot_gate.jsp?TARGET_URL=/jsp/main/main_0013_00.jsp&ISSU_ID=32E71049941F061A3075BA0C1CDEAF1DDB26B0437E67318E&SEQ_NO=2026052941000026zzzreov0_149713956535295956_1&CORP_TYPE=BUYR"

driver = _make_driver(headless=True)
try:
    _selenium_login(driver, 'https://ngwx.ktbizoffice.com')

    print("taxbill 페이지 접속 중...")
    driver.get(TAXBILL_URL)
    time.sleep(5)
    print("현재 URL:", driver.current_url)

    # JS로 모든 frame 텍스트 (chr 대신 \n 사용)
    page_text = driver.execute_script(
        "var t=[];"
        "try{t.push(document.body.innerText);}catch(e){}"
        "for(var i=0;i<window.frames.length;i++){"
        "  try{t.push(window.frames[i].document.body.innerText);}catch(e){}"
        "}"
        "return t.join('\n');"
    ) or ""
    print("--- page_text 길이:", len(page_text), "---")
    print(page_text[:2000])

    # frame switch 방식도 시도
    frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
    print("frame 수:", len(frames))
    for i, frm in enumerate(frames):
        try:
            driver.switch_to.frame(frm)
            txt = driver.execute_script("return document.body ? document.body.innerText : '';") or ""
            print(f"frame[{i}] 텍스트 ({len(txt)}자):", txt[:500])
            driver.switch_to.default_content()
        except Exception as e:
            driver.switch_to.default_content()

    # 스크린샷 저장
    driver.save_screenshot("downloads/taxbill_debug.png")
    print("스크린샷: downloads/taxbill_debug.png")
finally:
    driver.quit()
