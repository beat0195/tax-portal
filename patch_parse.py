import re, os, sys
sys.path.insert(0, r"C:\tax_portal")

# mail_collector.py patch
# Fix: _parse_taxbill_page uses frame[0] via execute_script
# Fix: run_full_pipeline saves parsed amounts to DB directly

target = r"C:\tax_portal\modules\mail_collector.py"
with open(target, encoding="utf-8") as f:
      code = f.read()

old = 'page_text = BeautifulSoup(driver.page_source, "html.parser").get_text()'
new = 'page_text = driver.execute_script("var f=window.frames[0];try{return f?f.document.body.innerText:document.body.innerText;}catch(e){return document.body.innerText||\'\';}") or ""'

if old in code:
      code = code.replace(old, new)
      print("patch1 OK: frame[0] innerText")
else:
      print("patch1 SKIP: already patched or not found")

with open(target, "w", encoding="utf-8") as f:
      f.write(code)

print("Done. Restart streamlit to apply.")
