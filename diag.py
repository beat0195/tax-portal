# -*- coding: utf-8 -*-
"""
diag.py - 메일 본문 링크 진단 스크립트
PowerShell 에서: python diag.py
"""
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

from modules.mail_collector import (
    _make_driver, _selenium_login,
    _get_mail_list_js, _get_mail_body_html,
    get_setting
)
from bs4 import BeautifulSoup

base_url = get_setting('groupware_url') or 'https://www.bizmeka.com'
print(f"[*] base_url = {base_url}")

driver = _make_driver(headless=True)
try:
    _selenium_login(driver, base_url)
    print("[*] 로그인 완료")

    mails = _get_mail_list_js(driver, base_url, max_count=200)
    print(f"[*] 메일 {len(mails)}건 조회")

    keywords = ['세금계산서', '필라테크', 'tax', 'taxbill', '계산서']
    targets = []
    for m in mails:
        subj = m.get('subject', '')
        for kw in keywords:
            if kw.lower() in subj.lower():
                targets.append(m)
                break

    print(f"[*] 세금계산서 관련 메일: {len(targets)}건")

    if not targets:
        print("[!] 세금계산서 관련 메일 없음. 첫 5건 제목:")
        for m in mails[:5]:
            print(f"    - {m.get('subject','(제목없음)')}")
    else:
        target = targets[0]
        print(f"[*] 분석 대상: {target.get('subject','')}")
        print(f"[*] href: {target.get('href','')}")

        html = _get_mail_body_html(driver, base_url, target['href'])
        print(f"[*] HTML 길이: {len(html)}")

        if len(html) < 10:
            print("[!] HTML 이 너무 짧음 - _get_mail_body_html 문제")
        else:
            soup = BeautifulSoup(html, 'html.parser')
            links = [a.get('href','') for a in soup.find_all('a', href=True)]
            print(f"[*] a href 링크 {len(links)}개:")
            for l in links:
                print(f"    - {l}")

            urls = list(set(re.findall(r'https?://[^\s\"<>]+', html)))
            print(f"[*] 정규식 URL {len(urls)}개:")
            for u in urls:
                print(f"    - {u[:120]}")

            print("[*] HTML 앞 500자:")
            print(html[:500])

finally:
    driver.quit()
    print("[*] 완료")
