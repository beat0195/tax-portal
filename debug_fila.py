import sys, time
sys.path.insert(0, '.')
from modules.mail_collector import _make_driver, _selenium_login, _get_mail_list_js, _get_mail_body_url

driver = _make_driver(headless=True)
try:
    _selenium_login(driver, 'https://ngwx.ktbizoffice.com')
    mails = _get_mail_list_js(driver, 'https://ngwx.ktbizoffice.com', keyword='', max_count=500)
    fila_list = [m for m in mails if '필라' in m.get('subject','') or '필라' in m.get('sender','')]
    print(f'필라테크 메일: {len(fila_list)}개')
    if not fila_list:
        print('필라테크 메일 없음')
    else:
        fila = fila_list[0]
        mail_url = _get_mail_body_url('https://ngwx.ktbizoffice.com', fila.get('id',''))
        print('mail_url:', mail_url)
        driver.get(mail_url)
        time.sleep(4)

        # JS로 모든 frame href 수집
        js = (
            "var h=[];"
            "function gl(d){var t=d.querySelectorAll('a');for(var i=0;i<t.length;i++){h.push(t[i].href||t[i].getAttribute('href')||'');} }"
            "try{gl(document);}catch(e){}"
            "for(var i=0;i<window.frames.length;i++){try{gl(window.frames[i].document);}catch(e){}}"
            "return h;"
        )
        hrefs = driver.execute_script(js) or []
        print(f'JS href {len(hrefs)}개:')
        for h in hrefs:
            if h:
                print(' ', h[:120])

        # Selenium frame switch
        from selenium.webdriver.common.by import By
        from bs4 import BeautifulSoup
        frames = driver.find_elements(By.TAG_NAME, 'frame') + driver.find_elements(By.TAG_NAME, 'iframe')
        print(f'frames: {len(frames)}개')
        for i, frm in enumerate(frames):
            try:
                driver.switch_to.frame(frm)
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                links = soup.find_all('a', href=True)
                print(f'  frame[{i}] links: {len(links)}개')
                for a in links:
                    print('   ', a['href'][:100])
                driver.switch_to.default_content()
            except Exception as e:
                print(f'  frame[{i}] error:', e)
                driver.switch_to.default_content()
finally:
    driver.quit()
