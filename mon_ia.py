import os
import json
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

API_KEY = os.environ.get("API_KEY", "...")
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
        self.data = {"facts": [], "messages": []}
        try:
            with open(self.file, encoding="utf-8") as f:
                self.data = json.load(f)
        except:
            pass
    def save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
    def add(self, role, content):
        self.data["messages"].append({"role": role, "content": content})
        self.data["messages"] = self.data["messages"][-60:]
        self.save()
    def add_fact(self, fact):
        if fact and fact not in self.data["facts"]:
            self.data["facts"].append(fact)
            self.data["facts"] = self.data["facts"][-30:]
            self.save()

MEMS = {}
def get_mem(user):
    if user not in MEMS:
        MEMS[user] = Memory(user)
    return MEMS[user]

def ask_gemini(prompt, mem):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
    system = f"Tu es JARVIS, assistant personnel, drôle et utile. Tu te souviens de l'utilisateur. Faits connus sur lui: {', '.join(mem.data.get('facts', []))}. Réponds en français, court et utile."
    body = json.dumps({"contents": [{"parts": [{"text": system + "\n\nUtilisateur: " + prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
            return d["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Erreur Gemini: {e}"

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>JARVIS</title><style>body{background:#000;color:#fff;font-family:sans-serif;margin:0;padding:20px;text-align:center}#chat{max-width:600px;margin:20px auto;text-align:left}.msg{padding:10px 14px;border-radius:14px;margin:8px 0;background:#111}.me{background:#004466;text-align:right}input{padding:14px;border-radius:14px;border:1px solid #333;background:#111;color:#fff;width:70%;font-size:15px}button{background:#00d4ff;border:none;padding:14px 20px;border-radius:14px;font-weight:800;cursor:pointer}</style></head><body>
<div id="loginOverlay" style="position:fixed;inset:0;z-index:9999;background:#000;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;padding:20px">
  <div style="font-size:32px;font-weight:800;letter-spacing:8px">J A R V I S</div>
  <div style="color:#888;font-size:13px">Chacun son JARVIS perso</div>
  <input id="loginPseudo" placeholder="Ton pseudo" style="padding:14px;border-radius:14px;border:1px solid #333;background:#111;color:#fff;width:280px;font-size:16px">
  <input id="loginCode" placeholder="Ton code secret" type="password" style="padding:14px;border-radius:14px;border:1px solid #333;background:#111;color:#fff;width:280px;font-size:16px">
  <button onclick="doLogin()" style="background:#00d4ff;border:none;padding:14px 20px;border-radius:14px;font-weight:800;width:280px;cursor:pointer">ENTRER DANS MON JARVIS</button>
  <p id="loginErr" style="color:#ff5555;font-size:13px"></p>
</div>
<h1>JARVIS</h1><div id="chat"></div><input id="inp" placeholder="Parle à JARVIS..."><button onclick="send()">ENVOYER</button>
<script>
let USER = localStorage.getItem('jarvis_user') || '';
let CODE = localStorage.getItem('jarvis_code') || '';
function doLogin(){
  let u = document.getElementById('loginPseudo').value.trim();
  let c = document.getElementById('loginCode').value.trim();
  if(!u || !c){ document.getElementById('loginErr').innerText = 'Mets un pseudo + un code'; return; }
  localStorage.setItem('jarvis_user', u);
  localStorage.setItem('jarvis_code', c);
  USER = u; CODE = c;
  document.getElementById('loginOverlay').style.display = 'none';
  loadHistory();
}
if(USER && CODE){ document.getElementById('loginOverlay').style.display = 'none'; }
async function loadHistory(){
  let r = await fetch('/history', {headers:{'X-User':USER,'X-Code':CODE}});
  let d = await r.json();
  let chat = document.getElementById('chat');
  chat.innerHTML = '';
  (d.messages||[]).forEach(m=>{ let div=document.createElement('div'); div.className='msg'+(m.role=='user'?' me':''); div.innerText=m.content; chat.appendChild(div); });
}
async function send(){
  let inp = document.getElementById('inp');
  let txt = inp.value.trim(); if(!txt) return;
  inp.value='';
  let chat = document.getElementById('chat');
  let div=document.createElement('div'); div.className='msg me'; div.innerText=txt; chat.appendChild(div);
  let r = await fetch('/chat', {method:'POST', headers:{'Content-Type':'application/json','X-User':USER,'X-Code':CODE}, body: JSON.stringify({message: txt})});
  let d = await r.json();
  let div2=document.createElement('div'); div2.className='msg'; div2.innerText=d.reply || d.error || 'Erreur'; chat.appendChild(div2);
  window.scrollTo(0, document.body.scrollHeight);
}
if(USER && CODE) loadHistory();
</script></body></html>"""

ADMIN_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Admin JARVIS</title><style>body{background:#000;color:#fff;font-family:sans-serif;padding:20px} input{padding:12px;border-radius:10px;border:none;width:250px} button{background:#00d4ff;border:none;padding:12px 20px;border-radius:10px;font-weight:bold;cursor:pointer} .user{background:#111;padding:15px;border-radius:15px;margin:15px 0;text-align:left} .msg{padding:8px;background:#222;border-radius:8px;margin:5px 0} .me{background:#004466;text-align:right}</style></head><body><h1>Panel Admin</h1><input id="code" type="password" placeholder="Code admin"><button onclick="load()">VOIR</button><div id="list"></div><script>async function load(){let code=document.getElementById('code').value;let r=await fetch('/admin_data',{headers:{'X-Admin':code}});let d=await r.json();if(d.error){alert(d.error);return}let h='';d.users.forEach(u=>{h+='<div class="user"><h3>'+u.name+' - '+u.messages.length+' messages - faits: '+(u.facts.join(' | ')||'aucun')+'</h3>';u.messages.slice(-20).forEach(m=>{h+='<div class="msg'+(m.role=='user'?' me':'')+'"><b>'+m.role+':</b> '+m.content+'</div>'});h+='</div>'});document.getElementById('list').innerHTML=h||'Aucun utilisateur pour le moment';}</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/admin":
            self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers()
            self.wfile.write(ADMIN_HTML.encode()); return
        if self.path == "/admin_data":
            if self.headers.get("X-Admin") != ADMIN_CODE:
                self.send_response(403); self.send_header("Content-Type","application/json"); self.end_headers()
                self.wfile.write(json.dumps({"error":"Code admin faux"}).encode()); return
            users = load_users()
            out=[]
            for name in users:
                m = get_mem(name)
                out.append({"name": name, "facts": m.data.get("facts",[]), "messages": m.data.get("messages",[])})
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps({"users": out}).encode()); return
        if self.path == "/history":
            user = check_auth(self.headers)
            if user is None or user is False:
                self.send_response(401); self.send_header("Content-Type","application/json"); self.end_headers()
                self.wfile.write(json.dumps({"error":"Non autorisé"}).encode()); return
            mem = get_mem(user)
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps({"messages": mem.data.get("messages",[])}).encode()); return
        self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers()
        self.wfile.write(HTML.encode())
    def do_POST(self):
        if self.path != "/chat":
            self.send_response(404); self.end_headers(); return
        user = check_auth(self.headers)
        if user is None or user is False:
            self.send_response(401); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps({"error":"Pseudo ou code faux"}).encode()); return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        msg = body.get("message","").strip()
        if not msg:
            self.send_response(400); self.end_headers(); return
        mem = get_mem(user)
        mem.add("user", msg)
        low = msg.lower()
        if "je m'appelle" in low or "mon nom" in low or "je suis" in low:
            mem.add_fact(msg)
        reply = ask_gemini(msg, mem)
        mem.add("assistant", reply)
        self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
        self.wfile.write(json.dumps({"reply": reply}).encode())
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"JARVIS sur port {port} - Admin: /admin")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
