with open(r'c:\tax_portal\modules\mail_collector.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """            if not vendor:
                for v in find_vendor_by_name("필라테크") + find_vendor_by_name("피엔씨") :
                    if v["name"].replace("(주)","").replace(" ","") in subject.replace("(주)","").replace(" ",""):
                        vendor = v
                        break"""

new = """            if not vendor:
                vendor = find_vendor_by_name(sender_name) if sender_name else None"""

if old in content:
    content = content.replace(old, new)
    with open(r'c:\tax_portal\modules\mail_collector.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK")
else:
    print("Block not found")
