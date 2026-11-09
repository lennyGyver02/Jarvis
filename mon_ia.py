import os
import json
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

API_KEY = os.environ.get("GROQ_API_KEY", "") or os.environ.get("API_KEY", "")
ADMIN_CODE = os.environ.get("ADMIN_CODE", "JARVIS-ADMIN-123")

def safe_user(s):
    s = re.sub(r'[^a-zA-Z0-9_-]', '', (s or '').lower().strip())
    return s[:20] or "invite"

def load_users():
    try:
        with open("users.json", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}
def save_users(u):
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(u, f)

def check_auth(headers):
    user = safe_user(headers.get("X-User"))
    code = headers.get("X-Code", "")
    if not user or not code:
        return None
    users = load_users()
    if user in users:
        if users[user] != code:
            return False
    else:
        users[user] = code
        save_users(users)
    return user

class Memory:
    def __init__(self, user):
        self.user = user
        self.file = f"memory_{user}.json"
        self.data = {"facts": [], "messages": [], "chats": [{"id": 1, "title": "Chat 1", "messages": []}]}
        try:
            with open(self.file, encoding="utf-8") as f:
                d = json.load(f)
                # compat ancien format
                if "chats" not in d:
                    d["chats"] = [{"id": 1, "title": "Chat 1", "messages": d.get("messages", [])}]
                self.data = d
        except:
            pass
    def save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
    def current_chat(self):
        if not self.data["chats"]:
            self.data["chats"] = [{"id": 1, "title": "Chat 1", "messages": []}]
        return self.data["chats"][-1]
    def add(self, role, content):
        c = self.current_chat()
        c["messages"].append({"role": role, "content": content})
        c["messages"] = c["messages"][-60:]
        if len(c["messages"]) == 1 and role == "user":
            c["title"] = content[:20]
        self.data["messages"] = c["messages"]
        self.save()
    def add_fact(self, fact):
        if fact and fact not in self.data["facts"]:
            self.data["facts"].append(fact)
            self.data["facts"] = self.data["facts"][-30:]
            self.save()
    def new_chat(self):
        nid = max([c["id"] for c in self.data["chats"]], default=0) + 1
        self.data["chats"].append({"id": nid, "title": f"Chat {nid}", "messages": []})
        self.save()
        return nid
    def clear_all(self):
        self.data = {"facts": [], "messages": [], "chats": [{"id": 1, "title": "Chat 1", "messages": []}]}
        self.save()

MEMS = {}
def get_mem(user):
    if user not in MEMS:
        MEMS[user] = Memory(user)
    return MEMS[user]

def ask_groq(prompt, mem):
    if not API_KEY:
        return "Erreur : GROQ_API_KEY manquante dans Render > Environment"
    url = "https://api.groq.com/openai/v1/chat/completions"
    system = f"Tu es JARVIS 9.4.5, assistant personnel, drôle et utile. Tu te souviens de l'utilisateur. Faits connus: {', '.join(mem.data.get('facts', []))}. Réponds en français, court et utile."
    body = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.7
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
            return d["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Erreur : {e}"

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>JARVIS 9.4.5</title><style>
*{box-sizing:border-box}body{margin:0;font-family:sans-serif;background:#050514;color:#fff;display:flex;height:100vh;overflow:hidden}
.sidebar{width:260px;background:linear-gradient(180deg,#1e6fd9,#7b2ff7);padding:20px;display:flex;flex-direction:column;gap:16px;flex-shrink:0}
.sidebar h1{font-size:28px;letter-spacing:10px;margin:0}.sidebar small{font-size:10px;opacity:.8}
.btn-new{background:linear-gradient(90deg,#4aa8ff,#b04aff);border:none;color:#fff;padding:14px;border-radius:14px;font-weight:800;cursor:pointer;font-size:15px}
.chat-item{background:rgba(255,255,255,.15);padding:12px;border-radius:12px;cursor:pointer}
.chat-item b{display:block}.chat-item span{font-size:12px;opacity:.8}
.sidebar .foot{margin-top:auto;font-size:11px;opacity:.8;line-height:1.6}
.main{flex:1;display:flex;flex-direction:column;background:radial-gradient(circle at 70% 20%,#1a1a4a,#050514 60%);position:relative;overflow:hidden}
.topbar{display:flex;justify-content:flex-end;padding:14px}
.btn-mem{background:#222;border:1px solid #555;color:#fff;padding:10px 14px;border-radius:20px;cursor:pointer;font-size:12px}
.orb-wrap{text-align:center;padding:10px}
.orb{width:140px;height:140px;margin:0 auto;border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff,#a78bfa 40%,#3b82f6 70%,#1e1b4b);box-shadow:0 0 60px #7c3aed;display:flex;align-items:center;justify-content:center;font-size:40px}
.online{letter-spacing:4px;font-size:12px;color:#7dd3fc;margin-top:10px}
#chat{flex:1;overflow-y:auto;padding:20px 30px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:75%;padding:14px 16px;border-radius:18px;background:rgba(255,255,255,.12);backdrop-filter:blur(10px);line-height:1.5;white-space:pre-wrap}
.msg.me{align-self:flex-end;background:linear-gradient(90deg,#2563eb,#7c3aed)}
.msg .head{font-size:11px;letter-spacing:2px;opacity:.7;display:flex;justify-content:space-between;gap:20px}
.msg .head button{background:none;border:none;color:#fff;cursor:pointer;font-size:11px}
.inputbar{padding:16px 24px 20px}
.inputbox{display:flex;align-items:center;gap:10px;background:linear-gradient(90deg,#1e40af,#7c3aed);padding:8px 8px 8px 14px;border-radius:40px}
.inputbox input{flex:1;background:transparent;border:none;outline:none;color:#fff;font-size:15px}
.inputbox input::placeholder{color:#ddd}
.circle{width:48px;height:48px;border-radius:50%;background:rgba(255,255,255,.3);border:none;color:#fff;font-size:22px;cursor:pointer;flex-shrink:0}
.send{background:#3b82f6}
.footer{text-align:center;font-size:10px;letter-spacing:4px;opacity:.6;padding-bottom:10px}
#loginOverlay{position:fixed;inset:0;z-index:9999;background:#000;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;padding:20px}
#loginOverlay input{padding:14px;border-radius:14px;border:1px solid #333;background:#111;color:#fff;width:280px;font-size:16px}
#loginOverlay button{background:#00d4ff;border:none;padding:14px 20px;border-radius:14px;font-weight:800;width:280px;cursor:pointer}
@media(max-width:700px){.sidebar{display:none}}
</style></head><body>
<div id="loginOverlay"><div style="font-size:32px;font-weight:800;letter-spacing:8px">J A R V I S</div><div style="color:#888;font-size:13px">Chacun son JARVIS perso</div><input id="loginPseudo" placeholder="Ton pseudo"><input id="loginCode" placeholder="Ton code secret" type="password"><button onclick="doLogin()">ENTRER DANS MON JARVIS</button><p id="loginErr" style="color:#ff5555;font-size:13px"></p></div>
<div class="sidebar"><h1>JARVIS</h1><small>9.4.5 • IMAGE FIX VRAI • SANS CROP • 120b</small><button class="btn-new" onclick="newChat()">+ Nouveau Chat</button><div><div style="font-size:11px;letter-spacing:2px;opacity:.8">• TES CHATS • MEMOIRE GLOBALE</div><div id="chatList" style="display:flex;flex-direction:column;gap:10px;margin-top:10px"></div></div><div class="foot">Chaque nouveau chat se souvient des autres chats.<br>Image : 1 toutes les 45s<br>Le bouton MÉMOIRE en haut supprime TOUT.</div></div>
<div class="main"><div class="topbar"><button class="btn-mem" onclick="clearMem()">🗑 MÉMOIRE (TOUT SUPPRIMER)</button></div><div class="orb-wrap"><div class="orb">✦</div><div class="online">• SYSTEM ONLINE</div></div><div id="chat"></div><div class="inputbar"><div class="inputbox"><button class="circle" onclick="alert('Images : bientôt')">+</button><input id="inp" placeholder="Écris quelque chose à JARVIS... ou génère une image..." onkeydown="if(event.key==='Enter')send()"><button class="circle send" onclick="send()">➤</button></div></div><div class="footer">J A R V I S  9.4.5  •  IMAGE FIX VRAI  •  SANS CROP  •  LIQUID GLASS  •  GROQ AI</div></div>
<script>
let USER=localStorage.getItem('jarvis_user')||'';let CODE=localStorage.getItem('jarvis_code')||'';
function doLogin(){let u=document.getElementById('loginPseudo').value.trim();let c=document.getElementById('loginCode').value.trim();if(!u||!c){document.getElementById('loginErr').innerText='Mets un pseudo + un code';return}localStorage.setItem('jarvis_user',u);localStorage.setItem('jarvis_code',c);USER=u;CODE=c;document.getElementById('loginOverlay').style.display='none';loadHistory();}
if(USER&&CODE)document.getElementById('loginOverlay').style.display='none';
async function loadHistory(){let r=await fetch('/history',{headers:{'X-User':USER,'X-Code':CODE}});let d=await r.json();let chat=document.getElementById('chat');chat.innerHTML='';(d.messages||[]).forEach(m=>addMsg(m.role,m.content));let list=document.getElementById('chatList');list.innerHTML='';(d.chats||[]).forEach(c=>{let div=document.createElement('div');div.className='chat-item';div.innerHTML='<b>'+c.title+'</b><span>'+c.messages.length+' msg • '+(c.messages[0]?.content?.slice(0,15)||'')+'</span>';list.appendChild(div);});}
function addMsg(role,txt){let chat=document.getElementById('chat');let div=document.createElement('div');div.className='msg'+(role=='user'?' me':'');div.innerHTML='<div class="head"><span>'+(role=='user'?'TOI':'JARVIS')+'</span><button onclick="navigator.clipboard.writeText(this.parentElement.parentElement.innerText)">📋 Copier</button></div><div>'+txt.replace(/</g,'&lt;')+'</div>';chat.appendChild(div);chat.scrollTop=chat.scrollHeight;}
async function send(){let inp=document.getElementById('inp');let txt=inp.value.trim();if(!txt)return;inp.value='';addMsg('user',txt);let r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json','X-User':USER,'X-Code':CODE},body:JSON.stringify({message:txt})});let d=await r.json();addMsg('assistant',d.reply||d.error||'Erreur');loadHistory();}
async function newChat(){await fetch('/new_chat',{method:'POST',headers:{'X-User':USER,'X-Code':CODE}});loadHistory();document.getElementById('chat').innerHTML='';}
async function clearMem(){if(!confirm('Supprimer TOUTE la mémoire ?'))return;await fetch('/clear',{method:'POST',headers:{'X-User':USER,'X-Code':CODE}});loadHistory();document.getElementById('chat').innerHTML='';}
if(USER&&CODE)loadHistory();
</script></body></html>"""

ADMIN_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Admin JARVIS</title><style>body{background:#000;color:#fff;font-family:sans-serif;padding:20px} input{padding:12px;border-radius:10px;border:none;width:250px} button{background:#00d4ff;border:none;padding:12px 20px;border-radius:10px;font-weight:bold;cursor:pointer} .user{background:#111;padding:15px;border-radius:15px;margin:15px 0;text-align:left} .msg{padding:8px;background:#222;border-radius:8px;margin:5px 0} .me{background:#004466;text-align:right}</style></head><body><h1>Panel Admin</h1><input id="code" type="password" placeholder="Code admin"><button onclick="load()">VOIR</button><div id="list"></div><script>async function load(){let code=document.getElementById('code').value;let r=await fetch('/admin_data',{headers:{'X-Admin':code}});let d=await r.json();if(d.error){alert(d.error);return}let h='';d.users.forEach(u=>{h+='<div class="user"><h3>'+u.name+' - '+u.messages.length+' messages - faits: '+(u.facts.join(' | ')||'aucun')+'</h3>';u.messages.slice(-20).forEach(m=>{h+='<div class="msg'+(m.role=='user'?' me':'')+'"><b>'+m.role+':</b> '+m.content+'</div>'});h+='</div>'});document.getElementById('list').innerHTML=h||'Aucun utilisateur pour le moment';}</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        self.send_response(code); self.send_header("Content-Type","application/json"); self.end_headers()
        self.wfile.write(json.dumps(obj).encode())
    def _html(self, html):
        self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers()
        self.wfile.write(html.encode())
    def do_GET(self):
        if self.path == "/admin":
            return self._html(ADMIN_HTML)
        if self.path == "/admin_data":
            if self.headers.get("X-Admin") != ADMIN_CODE:
                return self._json(403, {"error":"Code admin faux"})
            users = load_users(); out=[]
            for name in users:
                m = get_mem(name)
                out.append({"name": name, "facts": m.data.get("facts",[]), "messages": m.data.get("messages",[]), "chats": m.data.get("chats",[])})
            return self._json(200, {"users": out})
        if self.path == "/history":
            user = check_auth(self.headers)
            if user is None or user is False:
                return self._json(401, {"error":"Non autorisé"})
            mem = get_mem(user)
            return self._json(200, {"messages": mem.current_chat()["messages"], "chats": mem.data.get("chats",[]), "facts": mem.data.get("facts",[])})
        return self._html(HTML)
    def do_POST(self):
        user = check_auth(self.headers)
        if user is None or user is False:
            return self._json(401, {"error":"Pseudo ou code faux"})
        mem = get_mem(user)
        if self.path == "/new_chat":
            mem.new_chat(); return self._json(200, {"ok": True})
        if self.path == "/clear":
            mem.clear_all(); return self._json(200, {"ok": True})
        if self.path != "/chat":
            return self._json(404, {"error":"not found"})
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        msg = body.get("message","").strip()
        if not msg:
            return self._json(400, {"error":"message vide"})
        mem.add("user", msg)
        low = msg.lower()
        if "je m'appelle" in low or "mon nom" in low or "je suis" in low:
            mem.add_fact(msg)
        reply = ask_groq(msg, mem)
        mem.add("assistant", reply)
        return self._json(200, {"reply": reply})
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"JARVIS 9.4.5 sur port {port} - Admin: /admin - GROQ: {'OK' if API_KEY else 'MANQUANTE'}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
