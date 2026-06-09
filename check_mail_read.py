import sys, time, json
sys.path.insert(0, r'c:\tax_portal')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

opts = Options()
opts.add_argument("--ignore-certificate-errors")
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

driver = webdriver.Chrome(options=opts)

# 1. 그룹웨어 로그인 페이지
driver.get("https://ngwx.ktbizoffice.com/LoginN.aspx?compid=obase")
print("=== 브라우저 열림 ===")
print("1. 로그인 해주세요")
print("2. 세금계산서 메일을 클릭해서 열어주세요")
print("3. 열린 후 Enter 키를 눌러주세요")
input("준비되면 Enter...")

# 현재 URL 확인
print("현재 URL:", driver.current_url)

# 네트워크 로그에서 mail_read URL + 세금계산서 링크 찾기
logs = driver.get_log("performance")
print("\n=== 네트워크 요청 중 관련 URL ===")
for log in logs:
    try:
        msg = json.loads(log["message"])["message"]
        if msg.get("method") == "Network.requestWillBeSent":
            url = msg.get("params", {}).get("request", {}).get("url", "")
            if any(k in url.lower() for k in ["mail_read", "etax", "tax", "invoice", "bill", "계산서"]):
                print(url)
    except:
        pass

# 페이지 내 링크 확인
print("\n=== 페이지 내 링크 ===")
links = driver.find_elements(By.TAG_NAME, "a")
for a in links:
    href = a.get_attribute("href") or ""
    text = a.text.strip()
    if href and len(href) > 10:
        print(f"[{text}] {href}")

# iframe 내부도 확인
iframes = driver.find_elements(By.TAG_NAME, "iframe")
print(f"\niframe 수: {len(iframes)}")
for i, iframe in enumerate(iframes):
    src = iframe.get_attribute("src") or ""
    print(f"iframe[{i}] src: {src}")

driver.quit()
