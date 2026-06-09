with open(r'c:\tax_portal\database.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

lines = content.split('\n')
clean_lines = [l for l in lines if '\ufffd' not in l and 'find_vendor_by_name' not in l and 'vname' not in l and 'sname' not in l]
clean_content = '\n'.join(clean_lines).rstrip()

joo = u"\uc8fc\uc2dd\ud68c\uc0ac"
joo2 = u"(\uc8fc)"

new_func = u"""

def find_vendor_by_name(name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vendors WHERE is_active = 1")
    vendors = cursor.fetchall()
    conn.close()
    for v in vendors:
        vname = v["name"].replace(u"(\uc8fc)", "").replace(u"\uc8fc\uc2dd\ud68c\uc0ac", "").strip()
        sname = name.replace(u"(\uc8fc)", "").replace(u"\uc8fc\uc2dd\ud68c\uc0ac", "").strip()
        if vname in sname or sname in vname:
            return dict(v)
    return None
"""

with open(r'c:\tax_portal\database.py', 'w', encoding='utf-8') as f:
    f.write(clean_content + new_func)
print("OK")
