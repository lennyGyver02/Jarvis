import os, json, re, glob, traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from groq import Groq

API_KEY = os.environ.get("GROQ_API_KEY", "")
ADMIN_CODE = os.environ.get("ADMIN_CODE", "1003")
client = Groq(api_key=API_KEY) if API_KEY else None
PORT = int(os.environ.get("PORT", 8000))

def safe_name(s):
    s = re.sub(r'[^a-zA-Z0-9_-]', '', (s or '').lower().strip())
    return s[:20] or "invite"

def load_mem(user):
    try:
        with open(f"memoire_{user}.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"facts": [], "messages": [], "code": ""}

def save_mem(user, mem):
    with open(f"memoire_{user}.json", "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False)

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>JARVIS</title><style>
body{background:#000;color:#fff;font-family:Arial,sans-serif;text-align:center;padding:15px;margin:0}
#login{background:#0a0a0a;padding:25px;border-radius:20px;max-width:360px;margin:60px auto;border:1px solid #222}
input{width:90%;padding:13px;margin:8px;border-radius:12px;border:1px solid #333;background:#111;color:#fff;font-size:16px}
button{background:#00d4ff;color:#000;border:none;padding:13px 20px;border-radius:12px;font-size:16px;font-weight:bold;cursor:pointer;width:95%}
#chat{display:none;max-width:650px;margin:auto}
#orb{width:130px;height:130px;border-radius:50%;background:radial-gradient(circle at 35% 35%, #aefaff, #00d4ff 40%, #004466 75%);margin:15px auto;box-shadow:0 0 60px #00d4ff, 0 0 120px #00d4ff55;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
#msgs{height:52vh;overflow:auto;text-align:left;background:#0a0a0a;border:1px solid #222;border-radius:20px;padding:15px;margin:12px 0}
.msg{margin:10px 0;padding:12px 14px;border-radius:16px;background:#1a1a1a;max-width:85%;line-height:1.4}
.me{background:#004466;margin-left:auto;text-align:right}
#box{display:flex;gap:8px} #q{flex:1}
.small{background:#222;color:#fff;margin-top:10px}
</style></head><body>
<div id="login"><div id="orb"></div><h1>JARVIS</h1><p>Ton assistant perso</p>
<input id="pseudo" placeholder="Ton pseudo"><input id="code" placeholder="Ton code secret" type="password">
<button onclick="entrer()">ENTRER</button><p id="err" style="color:#ff5555"></p></div>
<div id="chat"><div id="orb"></div><h2 id="titre"></h2><div id="msgs"></div>
<div id="box"><input id="q" placeholder="Parle a JARVIS..."><button onclick="envoyer()">Envoyer</button></div>
<button class="small" onclick="localStorage.clear();location.reload()">Changer de compte</button></div>
<script>
let pseudo=localStorage.getItem('pseudo'), code=localStorage.getItem('code');
if(pseudo && code){showChat()}
function entrer(){
  pseudo=document.getElementById('pseudo').value.trim(); code=document.getElementById('code').value.trim();
  if(!pseudo||!code){document.getElementById('err').innerText='Mets un pseudo + un code';return}
  localStorage.setItem('pseudo',pseudo); localStorage.setItem('code',code); showChat();
}
function showChat(){document.getElementById('login').style.display='none';document.getElementById('chat').style.display='block';document.getElementById('titre').innerText='Salut '+pseudo;charger()}
async function charger(){
  let r=await fetch('/history',{headers:{'X-User':pseudo,'X-Code':code}}); let d=await r.json();
  if(d.error){alert(d.error);localStorage.clear();location.reload();return}
  let m=document.getElementById('msgs'); m.innerHTML='';
  d.messages.forEach(x=>{let div=document.createElement('div');div.className='msg'+(x.role=='user'?' me':'');div.innerText=x.content;m.appendChild(div)}); m.scrollTop=m.scrollHeight;
}
async function envoyer(){
  let inp=document.getElementById('q'); let txt=inp.value.trim(); if(!txt)return; inp.value='';
  let m=document.getElementById('msgs'); let div=document.createElement('div');div.className='msg me';div.innerText=txt;m.appendChild(div);
  let r=await fetch('/chat',{method:'POST',headers:{'X-User':pseudo,'X-Code':code,'Content-Type':'application/json'},body:JSON.stringify({message:txt})});
  let d=await r.json(); let div2=document.createElement('div');div2.className='msg';div2.innerText=d.reply||d.error;m.appendChild(div2); m.scrollTop=m.scrollHeight;
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')envoyer()});
</script></body></html>"""

ADMIN_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Admin JARVIS</title>
<style>body{background:#000;color:#fff;font-family:sans-serif;padding:20px} input{padding:12px;border-radius:10px;border:none;width:250px} button{background:#00d4ff;border:none;padding:12px 20px;border-radius:10px;font-weight:bold;cursor:pointer} .user{background:#111;padding:15px;border-radius:15px;margin:15px 0;text-align:left} .msg{padding:8px;background:#222;border-radius:8px;margin:5px 0} .me{background:#004466;text-align:right}</style>
</head><body><h1>Panel Admin</h1><input id="code" type="password" placeholder="Code admin"><button onclick="load()">VOIR</button><div id="list"></div>
<script>
async function load(){
  let code=document.getElementById('code').value;
  let r=await fetch('/admin_data',{headers:{'X-Admin':code}}); let d=await r.json();
  if(d.error){alert(d.error);return}
  let h='';
  d.users.forEach(u=>{
    h+='<div class="user"><h3>'+u.name+' - '+u.messages.length+' messages - faits: '+(u.facts.join(' | ')||'aucun')+'</h3>';
    u.messages.slice(-20).forEach(m=>{h+='<div class="msg'+(m.role=='user'?' me':'')+'"><b>'+m.role+':</b> '+m.content+'</div>'});
    h+='</div>';
  });
  document.getElementById('list').innerHTML=h||'Aucun utilisateur pour le moment';
}
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/admin":
            self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers(); self.wfile.write(ADMIN_HTML.encode()); return
        if self.path == "/admin_data":
            if self.headers.get("X-Admin","") != ADMIN_CODE:
                return self.send_json({"error":"Mauvais code admin"},403)
            users=[]
            for f in glob.glob("memoire_*.json"):
                try:
                    with open(f, encoding="utf-8") as fh: mem=json.load(fh)
                    users.append({"name":f.replace("memoire_","").replace(".json",""),"facts":mem.get("facts",[]),"messages":mem.get("messages",[])[-30:]})
                except: pass
            return self.send_json({"users":users})
        if self.path == "/history":
            user=safe_name(self.headers.get("X-User")); code=self.headers.get("X-Code","")
            mem=load_mem(user)
            if mem.get("code") and mem["code"]!=code:
                return self.send_json({"error":"Mauvais code pour ce pseudo ! Prends un autre pseudo."},403)
            return self.send_json({"messages":mem["messages"][-30:]})
        self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers(); self.wfile.write(HTML.encode())
    def do_POST(self):
        l=int(self.headers.get("Content-Length",0)); data=json.loads(self.rfile.read(l) or b"{}")
        user=safe_name(self.headers.get("X-User")); code=self.headers.get("X-Code","")
        mem=load_mem(user)
        if not mem.get("code"): mem["code"]=code
        if mem["code"]!=code: return self.send_json({"error":"Mauvais code !"},403)
        q=data.get("message","")
        mem["messages"].append({"role":"user","content":q})
        low=q.lower()
        if any(k in low for k in ["je m'appelle","je suis","j'habite","j'aime","mon anniversaire"]):
            if q not in mem["facts"]: mem["facts"].append(q)
        prompt=f"Tu es JARVIS, l'assistant perso de {user}. Ce que tu sais sur lui : {'; '.join(mem['facts'][-10:])}. Reponds en francais, cool, court, comme un pote."
        rep=None; err=""
        # On essaie 2 modeles, si le 1er est mort on prend le 2eme
        for model in ["llama-3.1-8b-instant", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"]:
            try:
                r=client.chat.completions.create(model=model,messages=[{"role":"system","content":prompt}]+mem["messages"][-10:],max_tokens=300)
                rep=r.choices[0].message.content; break
            except Exception as e:
                err=str(e); print(f"MODELE {model} ERREUR: {err}"); continue
        if not rep:
            rep=f"Erreur Groq : {err[:200]} - Verifie ta cle GROQ_API_KEY sur Render"
            print(traceback.format_exc())
        mem["messages"].append({"role":"assistant","content":rep}); save_mem(user,mem)
        self.send_json({"reply":rep})
    def send_json(self,obj,code=200):
        b=json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b)
    def log_message(self,*a): pass

HTTPServer(("0.0.0.0",PORT),H).serve_forever()
