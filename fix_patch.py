import sys
path = r"C:\tax_portal\modules\mail_collector.py"
with open(path, encoding="utf-8") as f:
      lines = f.readlines()
  changed = False
for i, line in enumerate(lines):
      if "page_text" in line and "page_source" in line and "BeautifulSoup" in line:
                indent = line[: len(line) - len(line.lstrip())]
                js1 = "var f=window.frames[0];"
                js2 = "try"
                js3 = "{return f?f.document.body.innerText:document.body.innerText;}"
                js4 = "catch(e)"
                js5 = "{return document.body.innerText||'';}"
                js = js1 + js2 + js3 + js4 + js5
                lines[i] = indent + 'page_text = (driver.execute_script("' + js + '") or "")\n'
                print("patched line", i+1, "->", repr(lines[i].strip()))
                changed = True
        if changed:
              with open(path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    print("DONE - mail_collector.py updated")
else:
    print("NOT FOUND - showing page_text lines:")
    for i, line in enumerate(lines):
              if "page_text" in line:
                            print(i+1, repr(line.strip()))
                
