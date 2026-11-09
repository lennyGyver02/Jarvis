# patch.py - rajoute ADMIN + CONNEXION + MEMOIRE SEPAREE sur ton JARVIS 9.4.5, sans toucher au design
import pathlib
p = pathlib.Path("mon_ia.py")
text = p.read_text(encoding="utf-8")

# 1. ADMIN_CODE + helpers users
text = text.replace(
    'API_KEY = API_KEY.strip().strip(\'"\').strip("\'").strip()',
    'API_KEY = API_KEY.strip().strip(\'"\').strip("\'").strip()\n'
    'ADMIN_CODE = os.environ.get("ADMIN_CODE", "JARVIS-ADMIN-123").strip()\n\n'
    'def safe_user(s):\n'
    '    s = "".join(c for c in (s or "").lower().strip() if c.isalnum() or c in "_-")\n'
    '    return s[:20] or "invite"\n'
    'def load_users():\n'
    '    try:\n'
    '        with open("users.json", encoding="utf-8") as f: return json.load(f)\n'
    '    except: return {}\n'
    'def save_users(u):\n'
    '    with open("users.json", "w", encoding="utf-8") as f: json.dump(u, f)\n'
    'def check_auth(headers):\n'
    '    u = safe_user(headers.get("X-User")); c = headers.get("X-Code", "")\n'
    '    if not u or not c: return None\n'
    '    users = load_users()\n'
    '    if u in users:\n'
    '        return False if users[u] != c else u\n'
    '    users[u] = c; save_users(users); return u\n'
)

# 2. Memoire separee par pseudo : jarvis_memory_lenny.db, jarvis_memory_teo.db...
text = text.replace(
    'class Memory:\n    def __init__(self):\n        self.c = sqlite3.connect(DB_PATH, check_same_thread=False)',
    'class Memory:\n    def __init__(self, user="default"):\n'
    '        self.user = user\n'
    '        _p = os.path.join(BASE_DIR, "jarvis_memory_" + user + ".db") if user != "default" else DB_PATH\n'
    '        self.c = sqlite3.connect(_p, check_same_thread=False)'
)
text = text.replace(
    'mem = Memory()',
    'MEMS = {}\n'
    'def get_mem(user):\n'
    '    if user not in MEMS: MEMS[user] = Memory(user)\n'
    '    return MEMS[user]\n'
    'mem = Memory("default")'
)

# 3. Routes /admin + /admin_data + auth sur GET
text = text.replace(
    "            if self.path=='/' or self.path=='/index.html':",
    "            if self.path=='/admin':\n"
    "                data=ADMIN_HTML.encode('utf-8'); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return\n"
    "            if self.path=='/admin_data':\n"
    "                if self.headers.get('X-Admin') != ADMIN_CODE:\n"
    "                    self.send_json({'error':'Code admin faux'}); return\n"
    "                out=[]\n"
    "                for _n in load_users():\n"
    "                    _m=get_mem(_n); _msgs=[]\n"
    "                    for _c in _m.list_chats(): _msgs.extend(_m.load(_c['id'],60))\n"
    "                    out.append({'name':_n,'facts':_m.load_facts(),'messages':_msgs,'chats':_m.list_chats()})\n"
    "                self.send_json({'users':out}); return\n"
    "            _user = check_auth(self.headers)\n"
    "            if _user is None or _user is False:\n"
    "                self.send_json({'error':'Non autorise'}); return\n"
    "            mem = get_mem(_user)\n"
    "            if self.path=='/' or self.path=='/index.html':"
)

# 4. Auth sur POST
text = text.replace(
    "            if self.path=='/clear':",
    "            _user2 = check_auth(self.headers)\n"
    "            if _user2 is None or _user2 is False:\n"
    "                self.send_json({'error':'Pseudo ou code faux'}); return\n"
    "            mem = get_mem(_user2)\n"
    "            if self.path=='/clear':",
    1
)

# 5. Page admin HTML
text = text.replace(
    'HTML = r"""',
    'ADMIN_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Admin JARVIS</title><style>body{background:#000;color:#fff;font-family:sans-serif;padding:20px}input{padding:12px;border-radius:10px;border:none;width:250px}button{background:#00d4ff;border:none;padding:12px 20px;border-radius:10px;font-weight:bold;cursor:pointer}.user{background:#111;padding:15px;border-radius:15px;margin:15px 0}.msg{padding:8px;background:#222;border-radius:8px;margin:5px 0}.me{background:#004466;text-align:right}</style></head><body><h1>Panel Admin JARVIS 9.4.5</h1><input id="code" type="password" placeholder="Code admin"><button onclick="load()">VOIR</button><div id="list"></div><script>async function load(){let code=document.getElementById('code').value;let r=await fetch('/admin_data',{headers:{'X-Admin':code}});let d=await r.json();if(d.error){alert(d.error);return}let h='';d.users.forEach(u=>{h+='<div class=user><h3>'+u.name+' - '+u.messages.length+' messages - faits: '+(u.facts.join(' | ')||'aucun')+'</h3>';u.messages.slice(-20).forEach(m=>{h+='<div class="msg'+(m.role=='user'?' me':'')+'"><b>'+m.role+':</b> '+m.content+'</div>'});h+='</div>'});document.getElementById('list').innerHTML=h||'Aucun utilisateur';}</script></body></html>"""\n\nHTML = r"""',
    1
)

# 6. Login overlay : CSS + HTML + JS
text = text.replace("<style>", "<style>\n#loginOverlay{position:fixed;inset:0;z-index:9999;background:#000;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;padding:20px}\n#loginOverlay input{padding:14px;border-radius:14px;border:1px solid #333;background:#111;color:#fff;width:280px;font-size:16px}\n#loginOverlay button{background:#00d4ff;border:none;padding:14px 20px;border-radius:14px;font-weight:800;width:280px;cursor:pointer;color:#000}", 1)
text = text.replace("</style></head><body>", "</style></head><body><div id=\"loginOverlay\"><div style=\"font-size:32px;font-weight:800;letter-spacing:8px\">J A R V I S</div><div style=\"color:#888;font-size:13px\">Chacun son JARVIS perso</div><input id=\"loginPseudo\" placeholder=\"Ton pseudo\"><input id=\"loginCode\" placeholder=\"Ton code secret\" type=\"password\"><button onclick=\"doLogin()\">ENTRER DANS MON JARVIS</button><p id=\"loginErr\" style=\"color:#ff5555;font-size:13px\"></p></div>", 1)
text = text.replace("let currentChatId=null", "let USER=localStorage.getItem('jarvis_user')||'';let CODE=localStorage.getItem('jarvis_code')||'';function doLogin(){let u=document.getElementById('loginPseudo').value.trim();let c=document.getElementById('loginCode').value.trim();if(!u||!c){document.getElementById('loginErr').innerText='Mets un pseudo + un code';return}localStorage.setItem('jarvis_user',u);localStorage.setItem('jarvis_code',c);USER=u;CODE=c;document.getElementById('loginOverlay').style.display='none';init();}function authH(e){return Object.assign({'X-User':USER,'X-Code':CODE},e||{});}if(USER&&CODE)document.getElementById('loginOverlay').style.display='none';\nlet currentChatId=null")
text = text.replace("await fetch('/chats')", "await fetch('/chats',{headers:authH()})")
text = text.replace("fetch('/chats/new',{method:'POST'})", "fetch('/chats/new',{method:'POST',headers:authH()})")
text = text.replace("fetch('/chats/'+id+'/delete',{method:'POST'})", "fetch('/chats/'+id+'/delete',{method:'POST',headers:authH()})")
text = text.replace("fetch('/clear',{method:'POST'})", "fetch('/clear',{method:'POST',headers:authH()})")
text = text.replace("fetch('/history?chat_id='+id)", "fetch('/history?chat_id='+id,{headers:authH()})")
text = text.replace("fetch('/chats/'+chatId+'/rename',{method:'POST',headers:{'Content-Type':'application/json'}", "fetch('/chats/'+chatId+'/rename',{method:'POST',headers:authH({'Content-Type':'application/json'})")
text = text.replace("fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'}", "fetch('/chat',{method:'POST',headers:authH({'Content-Type':'application/json'})")
text = text.replace("\ninit();\n</script>", "\nif(USER&&CODE)init();\n</script>")

p.write_text(text, encoding="utf-8")
print("PATCH OK - ton mon_ia.py est maintenant multi-user + admin, design intact")
