import sys, time, json
sys.path.insert(0, "c:/tax_portal")
from database import get_setting
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

base_url = "https://ngwx.ktbizoffice.com"
company  = get_setting("bizmeka_company") or "obase"
user_id  = get_setting("groupware_id")
pw       = get_setting("groupware_pw")

options = webdriver.ChromeOptions()
options.add_argument("--ignore-certificate-errors")
options.add_argument("--start-maximized")
options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 15)

try:
    driver.get(f"{base_url}/LoginN.aspx?compid={company}")
    wait.until(EC.presence_of_element_located((By.ID, "TextUserID")))
    driver.find_element(By.ID, "TextUserID").send_keys(user_id)
    driver.find_element(By.ID, "TextPassword").send_keys(pw)
    driver.find_element(By.ID, "LoginButton").click()
    time.sleep(5)

    # 1) 폴더 목록 조회 (받은편지함 FOLDERID 자동 취득)
    driver.get_log("performance")
    print("[1단계] 메일함 클릭 후 Enter...")
    input()
    time.sleep(2)

    logs = driver.get_log("performance")
    folder_id = ""
    for log in logs:
        msg = json.loads(log["message"])["message"]
        if msg.get("method") == "Network.requestWillBeSent":
            req = msg.get("params", {}).get("request", {})
            url = req.get("url", "")
            if "mail_get_list_cross" in url:
                post = req.get("postData", "")
                import re
                m = re.search(r"<FOLDERID>(.*?)</FOLDERID>", post)
                if m:
                    folder_id = m.group(1)
                    print(f"✅ FOLDERID 캡처: {folder_id[:60]}...")

    # 2) 메일 클릭 시 본문/첨부 URL 캡처
    driver.get_log("performance")
    print("\n[2단계] 세금계산서 메일 한 개 클릭 후 본문이 열리면 Enter...")
    input()
    time.sleep(3)

    logs2 = driver.get_log("performance")
    print("\n=== 메일 본문/첨부 관련 모든 요청 ===")
    for log in logs2:
        msg = json.loads(log["message"])["message"]
        if msg.get("method") in ("Network.requestWillBeSent", "Network.responseReceived"):
            method_type = msg.get("method")
            if method_type == "Network.requestWillBeSent":
                req = msg.get("params", {}).get("request", {})
                url = req.get("url", "")
                if "ngwx" in url and not any(x in url for x in [".gif",".png",".jpg",".css",".js","blank","organt"]):
                    print(f"  [{req.get('method')}] {url}")
                    if req.get("postData"):
                        print(f"    POST: {req['postData'][:300]}")

    input("\n종료하려면 Enter...")

finally:
    driver.quit()
