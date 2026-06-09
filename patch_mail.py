with open(r'c:\tax_portal\modules\mail_collector.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''            vendor = find_vendor_by_biz_number(biz_number) if biz_number else None
            status = 'MATCHED' if vendor else 'PENDING'
            vendor_id = vendor['id'] if vendor else None'''

new_block = '''            vendor = find_vendor_by_biz_number(biz_number) if biz_number else None
            if not vendor:
                from database import find_vendor_by_name
                vendor = find_vendor_by_name(sender_name)
            status = 'MATCHED' if vendor else 'PENDING'
            vendor_id = vendor['id'] if vendor else None'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(r'c:\tax_portal\modules\mail_collector.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK")
else:
    print("Block not found - relevant lines:")
    for i, l in enumerate(content.split('\n')):
        if any(k in l for k in ['find_vendor_by_biz', 'MATCHED', 'PENDING', 'vendor_id']):
            print(f"{i}: {l}")
