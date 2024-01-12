# Auslesen der PV-Leistung ünder das Kostal Web-Interace
import urllib

global last_value
if not 'last_value' in globals():
    last_value = 0
    
# Auslesen PV-Seite    
def read_pv_voltage():
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    top_level_url = "http://192.168.178.38"
    password_mgr.add_password(None, top_level_url, "pvserver", "pvwr")
    handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
    opener = urllib.request.build_opener(handler)
    try:
        f = opener.open(top_level_url)
    except Exception as e:
        print('exception reading pv-voltage')
        return last_value
  
    myfile = f.read()
    myfilestr = myfile.decode("utf-8");
    i = myfilestr.index('aktuell')
    splitstr=myfilestr[i+65:i+95]
    j = splitstr.index("</td>")
    result = splitstr[0:j]
    try:
        converted_num = int(result)
    except ValueError:
        converted_num = int("0")
    return converted_num
