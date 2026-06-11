# -*- coding: utf-8 -*-
"""
diag2.py - 메일 본문 URL 구조 탐색 진단
"""
import sys, re, time
sys.stdout.reconfigure(encoding='utf-8')

from modules.mail_collector import (
    _make_driver, _selenium_login,
    _get_mail_list_js, _get_mail_body_html,
    get_setting
)
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
import requests

base_url = get_setting('groupware_url') or 'https://www.bizmeka.com'
print(f"base_url = {base_url}")

driver = _make_driver(headless=False)  # 화면 보이게
try:
    _selenium_login(driver, base_url)
    print("로그인 완료")

    mails = _get_mail_list_js(driver, base_url, max_count=200)
    print(f"메일 {len(mails)}건 조회")

    # 세금계산서 관련 메일 찾기
    keywords = ['세금계산서', '필라테크', 'tax', '계산서', 'invoice']
    targets = [m for m in mails if any(kw.lower() in m.get('subject','').lower() for kw in keywords)]
    print(f"대상 메일: {len(targets)}건")

    if not targets:
        print("대상 없음. 첫 3건:")
        for m in mails[:3]:
            print(f"  - {m.get('subject','')}")
    else:
        target = targets[0]
        mail_id = target['href']
        print(f"\n=== 분석 대상 ===")
        print(f"제목: {target.get('subject','')}")
        print(f"mail_id (앞 80자): {mail_id[:80]}")

        # 방법 1: XML API mail_get_body.aspx
        print("\n--- 방법1: mail_get_body.aspx XML API ---")
        xml_body = "<DATA><MAILID>" + mail_id + "</MAILID><BODYTYPE>2</BODYTYPE></DATA>"
        js = ("var xhr = new XMLHttpRequest();"
              "xhr.open('POST', '/myoffice/ezEmail/remote/mail_get_body.aspx', false);"
              "xhr.setRequestHeader('Content-Type', 'text/xml; charset=utf-8');"
              "xhr.send(arguments[0]);"
              "return xhr.responseText;")
        xml_text = driver.execute_script(js, xml_body)
        print(f"  응답 길이: {len(xml_text) if xml_text else 0}")
        if xml_text:
            print(f"  응답 앞 300자: {xml_text[:300]}")

        # 방법 2: 다른 XML API 엔드포인트들 시도
        print("\n--- 방법2: 다른 API 엔드포인트 ---")
        endpoints = [
            '/myoffice/ezEmail/remote/mail_get_body_cross.aspx',
            '/myoffice/ezEmail/remote/mail_read.aspx',
            '/myoffice/ezEmail/mail_detail.aspx',
        ]
        for ep in endpoints:
            try:
                js2 = ("var xhr = new XMLHttpRequest();"
                       "xhr.open('POST', '" + ep + "', false);"
                       "xhr.setRequestHeader('Content-Type', 'text/xml; charset=utf-8');"
                       "xhr.send(arguments[0]);"
                       "return xhr.responseText;")
                resp = driver.execute_script(js2, xml_body)
                print(f"  {ep}: {len(resp) if resp else 0}자")
                if resp and len(resp) > 200:
                    print(f"    앞 200자: {resp[:200]}")
            except Exception as e:
                print(f"  {ep}: 오류 - {e}")

        # 방법 3: Selenium으로 메일 읽기 페이지 직접 접근
        print("\n--- 방법3: Selenium 직접 메일 열기 ---")
        # 메일 목록 페이지로 이동 후 메일 클릭
        driver.get(base_url + "/myoffice/main/index_myoffice.aspx?funCode=1")
        time.sleep(3)
        print(f"  현재 URL: {driver.current_url}")

        # 메일 링크 찾기
        all_links = driver.find_elements(By.TAG_NAME, "a")
        mail_links = [a for a in all_links if a.get_attribute("href") and "mail" in a.get_attribute("href","").lower()]
        print(f"  mail 링크 수: {len(mail_links)}")
        for a in mail_links[:3]:
            print(f"    href: {a.get_attribute('href')[:100]}")

        # iframes 확인
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        print(f"  iframe 수: {len(iframes)}")
        for i, fr in enumerate(iframes[:5]):
            src = fr.get_attribute("src") or ""
            name = fr.get_attribute("name") or fr.get_attribute("id") or ""
            print(f"    iframe[{i}] name={name} src={src[:80]}")

        # 방법 4: JS로 메일 목록 클릭 이벤트 찾기
        print("\n--- 방법4: JS 네트워크 요청 분석 ---")
        # 메일 id를 파라미터로 하는 GET URL 시도
        test_urls = [
            f"/myoffice/ezEmail/mail_view.aspx?id={requests.utils.quote(mail_id[:50])}",
            f"/myoffice/ezEmail/mail_read.aspx?mailid={requests.utils.quote(mail_id[:50])}",
        ]
        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])
        session.headers.update({'User-Agent': 'Mozilla/5.0'})

        for url in test_urls:
            try:
                full_url = base_url + url
                r = session.get(full_url, timeout=5, verify=False)
                print(f"  GET {url[:60]}: {r.status_code}, {len(r.text)}자")
                if r.status_code == 200 and len(r.text) > 500:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    links = [a['href'] for a in soup.find_all('a', href=True) if 'http' in a.get('href','')]
                    print(f"    링크 수: {len(links)}")
                    for l in links[:3]:
                        print(f"    - {l[:100]}")
            except Exception as e:
                print(f"  {url[:60]}: 오류 - {e}")

        # 방법 5: Performance log에서 실제 메일 읽기 XHR 찾기
        print("\n--- 방법5: 메일 클릭 후 Network 로그 ---")
        driver.get(base_url + "/myoffice/main/index_myoffice.aspx?funCode=1")
        time.sleep(4)
        # JS로 첫 메일 클릭 시뮬레이션
        js_click = """
        var rows = document.querySelectorAll('tr[onclick], td[onclick], div[onclick]');
        if(rows.length > 0) {
            return 'clickable rows: ' + rows.length + ', first onclick: ' + rows[0].getAttribute('onclick');
        }
        var links = document.querySelectorAll('a');
        var mailLinks = Array.from(links).filter(a => a.href && a.href.includes('mail'));
        return 'mail links: ' + mailLinks.length;
        """
        result = driver.execute_script(js_click)
        print(f"  페이지 클릭 요소: {result}")

finally:
    input("확인 후 Enter 키를 누르세요...")
    driver.quit()
    print("완료")
