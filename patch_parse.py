import re, sys
target = r"C:\tax_portal\modules\mail_collector.py"
with open(target, encoding="utf-8") as f:
          code = f.read()
      # show the actual line containing page_text
      for i, line in enumerate(code.splitlines(), 1):
                if "page_text" in line and ("BeautifulSoup" in line or "page_source" in line):
                              print(f"LINE {i}: {repr(line)}")
                      # patch: replace BeautifulSoup(driver.page_source...) with execute_script frame[0]
                      old = 'BeautifulSoup(driver.page_source, "html.parser").get_text()'
new = 'driver.execute_script("var f=window.frames[0];try{return f?f.document.body.innerText:document.body.innerText;}catch(e){return document.body.innerText||\'\';}") or ""'
if old in code:
          code = code.replace(old, new)
    print("patch OK: frame[0] innerText applied")
else:
    print("NOT FOUND - trying partial match")
    m = re.search(r'page_text\s*=\s*BeautifulSoup\(driver\.page_source.*?\.get_text\(\)', code)
    if m:
                  code = code[:m.start()] + "page_text = " + new + code[m.end():]
                  print("partial patch OK")
else:
        print("FAILED - no match found")
with open(target, "w", encoding="utf-8") as f:
          f.write(code)
print("Done.")
