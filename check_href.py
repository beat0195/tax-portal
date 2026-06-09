import sys, importlib.util
sys.path.insert(0, r'c:\tax_portal')

spec = importlib.util.spec_from_file_location("mc", r"c:\tax_portal\modules\mail_collector.py")
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)

session, base_url = mc.logingroupware()
if session:
    print("LOGIN OK, base_url:", base_url)
    folder_id = mc.getinbox_folder_id(session, base_url)
    print("folder_id:", folder_id)
    xml = mc.getmail_list(session, base_url, folder_id)
    if xml:
        open(r'c:\tax_portal\debug_mail.xml', 'w', encoding='utf-8').write(xml)
        print("XML saved, length:", len(xml))
        mails = mc.parsemail_list(xml)
        print("mails count:", len(mails))
        for m in mails[:3]:
            print(m)
    else:
        print("XML empty")
else:
    print("LOGIN FAILED")
