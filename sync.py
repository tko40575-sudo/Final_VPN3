import time
import requests
import urllib3
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# SSL Warning များကို ပိတ်ထားရန်
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# Firebase ချိတ်ဆက်ခြင်း
# ==========================================
# သတိပြုရန်: 'serviceAccountKey.json' သည် သင်၏ Firebase Admin SDK Key ဖြစ်ရမည်။
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def get_server_configs():
    """Admin Panel မှ လုံခြုံစွာထည့်ထားသော Server Credentials များကို လှမ်းယူခြင်း"""
    try:
        doc = db.collection("admin_config").document("server_api").get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        print(f"[-] Error fetching configs from Firebase: {e}")
    return None

def get_outline_usage(api_url):
    if not api_url: return {}
    try:
        res = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=10)
        return res.json().get('bytesTransferredByUserId', {})
    except Exception as e:
        print(f"[-] Outline Sync Error: {e}")
        return {}

def get_xui_usage(xui_url, xui_user, xui_pass):
    if not xui_url or not xui_user: return {}
    try:
        session = requests.Session()
        login_res = session.post(f"{xui_url}/login", data={'username': xui_user, 'password': xui_pass}, timeout=10)
        
        if login_res.status_code != 200:
            print("[-] X-UI Login Failed! Check Password in Admin Panel.")
            return {}
        
        res = session.get(f"{xui_url}/xui/API/inbounds", timeout=10)
        inbounds = res.json().get('obj', [])
        
        xui_usage = {}
        for inbound in inbounds:
            client_stats = inbound.get('clientStats', [])
            for client in client_stats:
                email = client.get('email', '')
                total_bytes = client.get('up', 0) + client.get('down', 0)
                xui_usage[email] = total_bytes
        return xui_usage
    except Exception as e:
        print(f"[-] X-UI Sync Error: {e}")
        return {}

def sync_data():
    print("[*] Checking secure server configs...")
    configs = get_server_configs()
    
    if not configs:
        print("[-] ⚠️ Server Configs missing! Please login to your Admin Panel and save your Server URLs & Passwords.")
        return

    print("[*] Connecting to VPN Servers privately...")
    outline_data = get_outline_usage(configs.get("outline_url"))
    xui_data = get_xui_usage(configs.get("xui_url"), configs.get("xui_user"), configs.get("xui_pass"))
    
    print("[*] Syncing data to Firebase Database...")
    users_ref = db.collection('users')
    docs = users_ref.stream()

    updated_count = 0
    for doc in docs:
        user_id = doc.id 
        user_data = doc.to_dict()
        update_fields = {}
        
        # Outline Sync
        outline_id = user_data.get('outlineId', user_id) 
        if outline_id in outline_data:
            used_gb = outline_data[outline_id] / (1024 ** 3)
            update_fields['outlineUsedGB'] = round(used_gb, 3)

        # X-UI (Vless) Sync
        if user_id in xui_data:
            used_gb = xui_data[user_id] / (1024 ** 3)
            update_fields['vlessUsedGB'] = round(used_gb, 3)

        if update_fields:
            users_ref.document(user_id).update(update_fields)
            updated_count += 1
            print(f"[+] Updated User {user_id}: {update_fields}")

    print(f"[*] Sync complete! Updated {updated_count} users successfully.")

if __name__ == "__main__":
    print("🚀 Private Secure Auto-Sync Started!")
    while True:
        sync_data()
        time.sleep(60) # ၁ မိနစ်တစ်ခါ Auto Update လုပ်မည်