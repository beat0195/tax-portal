# -*- coding: utf-8 -*-
"""
diag3.py - 그룹웨어 메일 페이지 구조 분석
"""
import sys, re, time
sys.stdout.reconfigure(encoding='utf-8')

from modules.mail_collector import (
    _make_driver, _selenium_login,
    _get_mail_list_js,
    get_setting
)
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
import requests

base_url = get_setting('groupware_url') or 'https://www.bizmeka.com'
print(f"base_url = {base_url}")

driver = _make_driver(headless=False)
try:
    _selenium_login(driver, base_url)
    print("로그인 완료")
    print(f"로그인 후 URL: {driver.current_url}")

    # 현재 페이지의 전체 프레임/iframe 구조 분석
    print("\n=== 로그인 후 페이지 구조 ===")
    print(f"Title: {driver.title}")

    # 모든 프레임 확인
    frames = driver.find_elements(By.TAG_NAME, "frame")
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"frame 수: {len(frames)}, iframe 수: {len(iframes)}")
    for i, f in enumerate(frames):
        src = f.get_attribute("src") or ""
        name = f.get_attribute("name") or f.get_attribute("id") or ""
        print(f"  frame[{i}] name={name} src={src[:100]}")
    for i, f in enumerate(iframes):
        src = f.get_attribute("src") or ""
        name = f.get_attribute("name") or f.get_attribute("id") or ""
        print(f"  iframe[{i}] name={name} src={src[:100]}")

    # 메일함 페이지로 이동
    print("\n=== funCode=1 메일함 이동 ===")
    driver.get(base_url + "/myoffice/main/index_myoffice.aspx?funCode=1")
    time.sleep(5)
    print(f"Title: {driver.title}")

    frames = driver.find_elements(By.TAG_NAME, "frame")
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"frame 수: {len(frames)}, iframe 수: {len(iframes)}")
    for i, f in enumerate(frames):
        src = f.get_attribute("src") or ""
        name = f.get_attribute("name") or f.get_attribute("id") or ""
        print(f"  frame[{i}] name={name} src={src[:120]}")

    # 페이지 소스 분석
    src_html = driver.page_source
    soup = BeautifulSoup(src_html, "html.parser")
    print(f"\n페이지 소스 길이: {len(src_html)}")
    # frameset 찾기
    framesets = soup.find_all("frameset")
    print(f"frameset 수: {len(framesets)}")
    for i, fs in enumerate(framesets):
        print(f"  frameset[{i}]: {str(fs)[:200]}")

    # 모든 frame src
    all_frames = soup.find_all(["frame", "iframe"])
    print(f"\n전체 frame/iframe: {len(all_frames)}개")
    for f in all_frames:
        src = f.get("src", "")
        name = f.get("name", f.get("id", ""))
        print(f"  name={name} src={src[:120]}")

    # 메일 목록 XML에서 실제 메일 읽기 href 확인
    print("\n=== 메일 목록 XML 원본 분석 ===")
    mails = _get_mail_list_js(driver, base_url, max_count=5)
    print(f"메일 {len(mails)}건")
    for m in mails[:3]:
        print(f"  subject: {m.get('subject','')[:60]}")
        print(f"  href: {m.get('href','')[:120]}")
        print(f"  from: {m.get('from','')[:60]}")
        print()

    # XML 원본 직접 가져오기
    print("\n=== 메일 목록 XML 원본 (첫 1000자) ===")
    folder_id = "AAMkAGUyNWIyYmU4LTBjM2MtNGM4OS04YTE4LWFhZjQ4ZTY3ZmE4ZAAuAAAAAACB7Z4ydzgUQo6MOiLN9ceFAQD2vFdoTp31Tb13wR9oUYV6AAAABH/bAAA="
    xml_body = ("<DATA><FOLDERID>" + folder_id + "</FOLDERID>"
                "<SORTTYPE> ORDER BY &quot;urn:schemas:httpmail:datereceived&quot; DESC</SORTTYPE>"
                "<SEARCH></SEARCH><START>0</START><END>2</END>"
                "<VIEWSELECTINDEX>0</VIEWSELECTINDEX></DATA>")
    js = ("var xhr = new XMLHttpRequest();"
          "xhr.open('POST', '/myoffice/ezEmail/remote/mail_get_list_cross.aspx', false);"
          "xhr.setRequestHeader('Content-Type', 'text/xml; charset=utf-8');"
          "xhr.send(arguments[0]);"
          "return xhr.responseText;")
    xml_raw = driver.execute_script(js, xml_body)
    print(xml_raw[:1500] if xml_raw else "응답 없음")

    # 메일 읽기 시도 - 실제 클릭으로 열기
    print("\n=== 메일 목록 첫 번째 항목 실제 클릭 시도 ===")
    driver.get(base_url + "/myoffice/main/index_myoffice.aspx?funCode=1")
    time.sleep(5)

    # 프레임 구조 재확인
    frames2 = driver.find_elements(By.TAG_NAME, "frame")
    print(f"frame 수: {len(frames2)}")
    for i, f in enumerate(frames2):
        src = f.get_attribute("src") or ""
        name = f.get_attribute("name") or ""
        print(f"  frame[{i}] name={name} src={src[:120]}")

    # 각 frame으로 전환해서 내부 확인
    for i, f in enumerate(frames2):
        try:
            name = f.get_attribute("name") or str(i)
            driver.switch_to.frame(f)
            title = driver.title
            cur_url = driver.current_url
            inner_html = driver.page_source[:300]
            # 내부 링크 확인
            inner_links = driver.find_elements(By.TAG_NAME, "a")
            onclick_els = driver.find_elements(By.XPATH, "//*[@onclick]")
            print(f"  frame[{i}] ({name}): title={title}, url={cur_url[:80]}")
            print(f"    links={len(inner_links)}, onclick={len(onclick_els)}")
            if onclick_els:
                for el in onclick_els[:3]:
                    print(f"    onclick: {el.get_attribute('onclick')[:120]}")
            driver.switch_to.default_content()
        except Exception as e:
            print(f"  frame[{i}] 전환 오류: {e}")
            driver.switch_to.default_content()

finally:
    input("확인 후 Enter...")
    driver.quit()
    print("완료")
