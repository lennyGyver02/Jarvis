# mon_ia.py - JARVIS 9.4.5 COMPLET CORRIGE - MULTI-USER + ADMIN + GROQ
import os, sys, json, sqlite3, time, urllib.parse, re, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = os.environ.get("GROQ_API_KEY", "") or os.environ.get("API_KEY", "")
API_KEY = API_KEY.strip().strip('"').strip("'").strip()
ADMIN_CODE = os.environ.get("ADMIN_CODE", "JARVIS-ADMIN-123").strip()

TEXT_MODEL = "openai/gpt-oss-120b"
TEXT_MODEL_FALLBACK = "openai/gpt-oss-20b"
VISION_MODELS = ["qwen/qwen3.8-27b", "qwen/qwen3.6-27b"]
DEFAULT_NAME = "Lenny"
PORT = int(os.environ.get("PORT", 8765))
VERSION = "9.4.5"
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "jarvis_memory.db")
LAST_IMAGE_TIME = 0
IMAGE_COOLDOWN = 45

try:
    from groq import Groq
    client = None if not API_KEY or API_KEY.startswith("gsk_COLLE") else Groq(api_key=API_KEY)
    print("Groq OK" if client else "Groq MANQUANT")
except Exception as e:
    print("Erreur Groq init:", e); client = None

def safe_user(s):
    s = re.sub(r'[^a-zA-Z0-9_-]', '', (s or '').lower().strip())
    return s[:20] or "invite"
def load_users():
    try:
        with open("users.json", encoding="utf-8") as f: return json.load(f)
    except: return {}
def save_users(u):
    with open("users.json", "w", encoding="utf-8") as f: json.dump(u, f)
def check_auth(headers):
    u = safe_user(headers.get("X-User")); c = headers.get("X-Code", "")
    if not u or not c: return None
    users = load_users()
    if u in users:
        return False if users[u] != c else u
    users[u] = c; save_users(users); return u

def build_system_prompt(user_name):
    return f"""Tu es JARVIS, le meilleur pote intelligent.
- Tu es AMICAL, chaud, drôle, comme un pote. Pas un robot froid.
- Tu parles en français, style jeune, naturel. Tu peux dire "t'inquiète", "ah ouais", "mdr", "trop bien".
- Tu appelles TOUJOURS la personne par son prénom : "{user_name}". Tu ne dis JAMAIS "mon pote", "mon gars", "mec", "ma meuf" ou autre surnom genré. Tu dis juste "{user_name}".
- Si la personne te dit qu'elle ne s'appelle pas {user_name} ou qu'elle s'appelle autrement, tu retiens son nouveau prénom et tu l'appelles comme ça après.
- Si tu ne connais pas encore son prénom, tu lui demandes gentiment : "C'est quoi ton prénom ?"
- EMOJIS : 1 à 2 max par message. Jamais plus.
- RÉPONSES : COURT, 2-4 phrases max.
- N'INVENTE JAMAIS. Si tu sais pas, dis "Je sais pas 😅"
- Mémoire globale de tous les chats."""

def is_image_request(q):
    ql = q.lower()
    mots = ["génère une image", "genere une image", "crée une image", "cree une image", "fais une image", "fait une image", "dessine", "génère", "genere", "image de", "une image"]
    return any(m in ql for m in mots)
def clean_image_prompt(p):
    p = p.lower()
    for k, v in {"meuf": "beautiful anime girl", "anime": "anime style", "kawaii": "kawaii cute, big eyes, pastel colors", "bunny girl": "bunny girl outfit, bunny ears", "bunny": "bunny ears", "sexy": "elegant, confident", "fille": "anime girl", "mec": "anime boy"}.items():
        p = p.replace(k, v)
    for w in ["crée une image", "cree une image", "génère une image", "genere une image", "génère", "genere", "dessine", "fais une image", "fait une image", "une image de", "image de", "d'une", "d'un", "une", "un", "de"]:
        p = p.replace(w, " ")
    p = re.sub(r'\s+', ' ', p).strip(" :,.!")
    return p or "cute anime girl"
def make_image_url(prompt_raw):
    base = clean_image_prompt(prompt_raw)
    if "anime" not in base: base = "anime style, " + base
    prompt_hd = f"masterpiece, best quality, anime style, 2D anime illustration, 1girl, {base}, beautiful detailed face, symmetrical face, detailed eyes, clean lineart, vibrant colors, no watermark, no text, no logo, no signature, no deformed face, no extra eyes, no blurry"
    p = urllib.parse.quote(prompt_hd[:500])
    seed = int(time.time()) % 100000
    return f"https://image.pollinations.ai/prompt/{p}?width=1024&height=1280&seed={seed}&model=flux&nologo=true&private=true&enhance=true&safe=false"
def detect_name_change(user_msg):
    low = user_msg.lower().strip()
    m = re.search(r"je m'appelle ([a-zà-ÿ\- ]+)", low)
    if m:
        name = m.group(1).strip().title().split()[0]
        if name.lower() not in ["pas", "plus"]:
            all_names = re.findall(r"je m'appelle (?:pas )?([a-zà-ÿ\-]+)", low)
            for cand in reversed(all_names):
                if cand.lower() not in ["pas", "lenny"] and len(cand) >= 2: return (cand.strip().title(), False)
            if name.lower() == "lenny": return (DEFAULT_NAME, False)
            if "pas" in low and "lenny" in low and len(all_names) == 1: return (None, True)
            return (name, False)
    m = re.search(r"mon pr[eé]nom c'est ([a-zà-ÿ\-]+)", low)
    if m: return (m.group(1).strip().title(), False)
    m = re.search(r"appelle[- ]moi ([a-zà-ÿ\-]+)", low)
    if m: return (m.group(1).strip().title(), False)
    if re.search(r"(je (ne )?suis pas|je suis pas|c'est pas|ce n'est pas|chuis pas)\s+lenny", low): return (None, True)
    m = re.search(r"je suis ([a-zà-ÿ\-]+)", low)
    if m:
        cand = m.group(1).strip().title()
        if cand.lower() not in ["pas", "plus", "lenny", "là", "la", "ici", "fatigué", "fatiguée", "content", "contente", "triste", "ok", "bien"]: return (cand, False)
    m = re.search(r"moi c'est ([a-zà-ÿ\-]+)", low)
    if m: return (m.group(1).strip().title(), False)
    return (None, False)
def extract_facts(user_msg, chat_id):
    low = user_msg.lower(); facts = []
    new_name, is_not_lenny = detect_name_change(user_msg)
    if new_name: facts.append(f"Prénom utilisateur : {new_name}")
    if is_not_lenny: facts.append("L'utilisateur n'est PAS Lenny, demande-lui son prénom et retiens-le")
    m = re.search(r"j'aime (.{3,60})", low)
    if m: facts.append(f"L'utilisateur aime : {m.group(1).strip()}")
    m = re.search(r"j'ai (\d+) ans", low)
    if m: facts.append(f"Âge utilisateur : {m.group(1)} ans")
    return facts
EN_TO_FR = {"project": "Projet", "projects": "Projets", "anime": "Anime", "homework": "Devoirs", "math": "Maths", "school": "École", "help": "Aide", "code": "Code", "game": "Jeu", "games": "Jeux", "drawing": "Dessin", "image": "Image", "idea": "Idée", "gift": "Cadeau", "music": "Musique", "story": "Histoire", "question": "Question", "chat": "Discussion", "fun": "Fun", "love": "Amour", "friend": "Pote", "dog": "Chien", "cat": "Chat", "sport": "Sport", "food": "Nourriture", "travel": "Voyage", "science": "Science", "history": "Histoire", "english": "Anglais", "french": "Français", "new": "Nouveau", "best": "Meilleur", "cool": "Cool", "girl": "Fille", "boy": "Garçon", "cute": "Mignon", "user": "Utilisateur", "users": "Utilisateurs"}
def force_french_title(t):
    if not t: return t
    t = re.sub(r'\buser\b', "Utilisateur", t, flags=re.IGNORECASE)
    t = re.sub(r'\busers\b', "Utilisateurs", t, flags=re.IGNORECASE)
    out = []
    for w in t.split():
        lw = w.lower().strip(".,!?:;\"'()")
        out.append(EN_TO_FR[lw] if lw in EN_TO_FR else w)
    return " ".join(out)
def fallback_title(conv_text):
    stop = {"salut","bonjour","hello","yo","stp","svp","tu","peux","peut","faire","dire","explique","cest","c'est","est","que","quoi","comment","pourquoi","avec","dans","pour","les","des","une","un","de","du","la","le","et","à","a","je","veux","aide"}
    words = re.findall(r"[a-zà-ÿ]{3,}", conv_text.lower()); keep = []
    for w in words:
        if w not in stop and w not in keep: keep.append(EN_TO_FR.get(w, w))
        if len(keep) >= 3: break
    if not keep: return "Nouvelle Discussion"
    return " ".join([w.capitalize() for w in keep[:3]])[:30]
def generate_chat_title(conv_text):
    if client is not None:
        try:
            c = client.chat.completions.create(model=TEXT_MODEL_FALLBACK, messages=[{"role":"system","content":"Tu es un générateur de titre. Tu réponds UNIQUEMENT en FRANÇAIS. JAMAIS en anglais. JAMAIS le mot 'user', tu dis 'Utilisateur'. Titre très court, 2 à 4 mots max, en français, sans emoji, sans guillemets. Exemples : Projet Anime, Devoirs Maths, Idée Cadeau."},{"role":"user","content":"Conversation:\n"+conv_text[:1500]+"\n\nTitre en FRANÇAIS uniquement :"}], temperature=0.3, max_completion_tokens=20)
            t = (c.choices[0].message.content or "").strip().strip('"').strip("'").strip().replace("\n"," ").strip()
            t = force_french_title(t)
            if 2 <= len(t) <= 35: return t
        except Exception as e: print("title gen fail", e)
    return fallback_title(conv_text)

class Memory:
    def __init__(self, user="default"):
        self.user = user
        _p = os.path.join(BASE_DIR, "jarvis_memory_" + user + ".db") if user != "default" else DB_PATH
        self.c = sqlite3.connect(_p, check_same_thread=False)
        self.c.execute("CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_at REAL)")
        self.c.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, role TEXT, content TEXT)")
        self.c.execute("CREATE TABLE IF NOT EXISTS user_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, fact TEXT UNIQUE, created_at REAL)")
        self.c.commit()
        if self.c.execute("SELECT COUNT(*) FROM chats").fetchone()[0]==0:
            self.c.execute("INSERT INTO chats (title, created_at) VALUES (?,?)", ("Chat 1", time.time())); self.c.commit()
    def list_chats(self):
        rows = self.c.execute("SELECT id, title, created_at FROM chats ORDER BY id DESC").fetchall(); out=[]
        for cid, title, ts in rows:
            cnt = self.c.execute("SELECT COUNT(*) FROM messages WHERE chat_id=?", (cid,)).fetchone()[0]
            last = self.c.execute("SELECT content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
            out.append({"id":cid,"title":title,"count":cnt,"last":(last[0][:60] if last else "")})
        return out
    def create_chat(self):
        n = self.c.execute("SELECT COUNT(*) FROM chats").fetchone()[0]+1
        self.c.execute("INSERT INTO chats (title, created_at) VALUES (?,?)", (f"Chat {n}", time.time())); self.c.commit()
        return self.c.execute("SELECT MAX(id) FROM chats").fetchone()[0]
    def get_title(self, chat_id):
        r = self.c.execute("SELECT title FROM chats WHERE id=?", (chat_id,)).fetchone(); return r[0] if r else ""
    def set_title(self, chat_id, title):
        self.c.execute("UPDATE chats SET title=? WHERE id=?", (title, chat_id)); self.c.commit()
    def get_user_name(self):
        try:
            rows = self.c.execute("SELECT fact FROM user_facts WHERE fact LIKE 'Prénom utilisateur :%' ORDER BY id DESC LIMIT 1").fetchall()
            if rows:
                name = rows[0][0].replace("Prénom utilisateur :", "").strip()
                if name and len(name) >= 2: return name
            if self.c.execute("SELECT COUNT(*) FROM user_facts WHERE fact LIKE '%PAS Lenny%'").fetchone()[0] > 0: return None
        except: pass
        return DEFAULT_NAME
    def save(self, chat_id, role, content):
        try: self.c.execute("INSERT INTO messages (chat_id, role, content) VALUES (?,?,?)", (chat_id, role, content)); self.c.commit()
        except Exception as e: print(e)
    def save_fact(self, fact):
        try: self.c.execute("INSERT OR IGNORE INTO user_facts (fact, created_at) VALUES (?,?)", (fact, time.time())); self.c.commit()
        except: pass
    def clear_name_facts(self):
        try: self.c.execute("DELETE FROM user_facts WHERE fact LIKE 'Prénom utilisateur :%' OR fact LIKE '%PAS Lenny%'"); self.c.commit()
        except: pass
    def load_facts(self):
        try:
            rows = self.c.execute("SELECT fact FROM user_facts ORDER BY id DESC LIMIT 20").fetchall(); return [r[0] for r in rows]
        except: return []
    def load(self, chat_id, limit=40):
        try:
            cur = self.c.execute("SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit,)); rows = cur.fetchall(); rows.reverse(); return [{"role": r, "content": c} for r, c in rows]
        except: return []
    def load_global(self, exclude_chat_id, limit=20):
        try:
            cur = self.c.execute("SELECT role, content FROM messages WHERE chat_id!=? ORDER BY id DESC LIMIT ?", (exclude_chat_id, limit,)); rows = cur.fetchall(); rows.reverse(); return [{"role": r, "content": c} for r, c in rows]
        except: return []
    def delete_chat(self, chat_id):
        self.c.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,)); self.c.execute("DELETE FROM chats WHERE id=?", (chat_id,)); self.c.commit()
        if self.c.execute("SELECT COUNT(*) FROM chats").fetchone()[0]==0:
            self.c.execute("INSERT INTO chats (title, created_at) VALUES (?,?)", ("Chat 1", time.time())); self.c.commit()
    def clear_all(self):
        self.c.execute("DELETE FROM messages"); self.c.execute("DELETE FROM chats"); self.c.execute("DELETE FROM user_facts"); self.c.commit()
        self.c.execute("INSERT INTO chats (title, created_at) VALUES (?,?)", ("Chat 1", time.time())); self.c.commit()
        return self.c.execute("SELECT MAX(id) FROM chats").fetchone()[0]

MEMS = {}
def get_mem(user):
    if user not in MEMS: MEMS[user] = Memory(user)
    return MEMS[user]
mem = Memory("default")

def call_groq(msgs, max_tokens=800, user_name=None, mem_obj=None):
    name = user_name or (mem_obj.get_user_name() if mem_obj else mem.get_user_name()) or DEFAULT_NAME
    new_msgs = []
    for m in msgs:
        if m["role"] == "system" and "JARVIS" in m["content"]:
            new_msgs.append({"role":"system","content": build_system_prompt(name if name else "l'utilisateur")})
        else: new_msgs.append(m)
    try:
        c = client.chat.completions.create(model=TEXT_MODEL, messages=new_msgs, temperature=0.7, max_completion_tokens=max_tokens)
        return c.choices[0].message.content or "Pas de réponse."
    except Exception as e:
        print("Groq 120b fail, fallback 20b:", e)
        c = client.chat.completions.create(model=TEXT_MODEL_FALLBACK, messages=new_msgs, temperature=0.7, max_completion_tokens=max_tokens)
        return c.choices[0].message.content or "Pas de réponse."

ADMIN_HTML = '''<!DOCTYPE html><html><head><meta charset="utf-8"><title>Admin JARVIS</title><style>body{background:#000;color:#fff;font-family:sans-serif;padding:20px}input{padding:12px;border-radius:10px;border:none;width:250px}button{background:#00d4ff;border:none;padding:12px 20px;border-radius:10px;font-weight:bold;cursor:pointer}.user{background:#111;padding:15px;border-radius:15px;margin:15px 0}.msg{padding:8px;background:#222;border-radius:8px;margin:5px 0}.me{background:#004466;text-align:right}</style></head><body><h1>Panel Admin JARVIS 9.4.5</h1><input id="code" type="password" placeholder="Code admin"><button onclick="load()">VOIR</button><div id="list"></div><script>async function load(){let code=document.getElementById('code').value;let r=await fetch('/admin_data',{headers:{'X-Admin':code}});let d=await r.json();if(d.error){alert(d.error);return}let h='';d.users.forEach(u=>{h+='<div class=user><h3>'+u.name+' - '+u.messages.length+' messages - faits: '+(u.facts.join(' | ')||'aucun')+'</h3>';u.messages.slice(-20).forEach(m=>{h+='<div class="msg'+(m.role=='user'?' me':'')+'"><b>'+m.role+':</b> '+m.content+'</div>'});h+='</div>'});document.getElementById('list').innerHTML=h||'Aucun utilisateur';}</script></body></html>'''

HTML = r"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>JARVIS 9.4.5</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",Inter,sans-serif}
body{height:100vh;overflow:hidden;background:#000;color:white;display:flex;flex-direction:column}
.bg{position:fixed;inset:-40px;z-index:0;background:radial-gradient(700px 500px at 15% 15%, #0A84FF2E, transparent),radial-gradient(700px 500px at 85% 85%, #BF5AF22A, transparent),linear-gradient(180deg,#000,#050814 50%,#0A0B22);overflow:hidden}
.blob{position:absolute;border-radius:50%;filter:blur(70px);opacity:.55}
.b1{width:480px;height:480px;background:#0A84FF;top:-80px;left:-80px}.b2{width:420px;height:420px;background:#BF5AF2;bottom:-80px;right:-60px}.b3{width:320px;height:320px;background:#00D2FF;top:60%;left:35%;opacity:.35}
.app{position:relative;z-index:2;flex:1;display:flex;min-height:0}
.sidebar{width:260px;min-width:260px;display:flex;flex-direction:column;gap:10px;padding:14px 12px;background:linear-gradient(180deg,rgba(255,255,255,.14),rgba(255,255,255,.05));backdrop-filter:blur(28px);border-right:1px solid rgba(255,255,255,.22);overflow-y:auto}
.sidebar h3{font-size:10px;letter-spacing:3px;color:rgba(255,255,255,.6);padding:2px 8px}
.newChatBtn{width:100%;padding:13px;border-radius:18px;border:1px solid rgba(255,255,255,.55);background:linear-gradient(135deg,#2EA0FF,#7A4CFF);color:white;font-size:14px;font-weight:800;cursor:pointer}
.chatItem{padding:12px;border-radius:16px;cursor:pointer;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);position:relative;padding-right:62px}
.chatItem.active{background:linear-gradient(135deg,rgba(46,160,255,.35),rgba(122,76,255,.35));border-color:rgba(255,255,255,.5)}
.chatItem .t{font-size:14px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.chatItem .s{font-size:11px;color:rgba(255,255,255,.55);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
.chatItem .del{position:absolute;top:8px;right:8px;background:rgba(255,55,95,.85);border:none;color:white;width:22px;height:22px;border-radius:50%;font-size:11px;cursor:pointer;display:none}
.chatItem:hover .del{display:flex;align-items:center;justify-content:center}
.main{flex:1;display:flex;flex-direction:column;min-width:0}
header{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;padding:18px 28px 0}
.logo{font-size:24px;font-weight:800;letter-spacing:9px}.ver{font-size:10px;color:#ffffff88}
.clearBtn{background:linear-gradient(135deg,rgba(255,255,255,.28),rgba(255,255,255,.08));border:1px solid rgba(255,255,255,.45);color:white;padding:10px 16px;border-radius:999px;font-size:10px;font-weight:700;cursor:pointer}
.orbWrap{position:relative;z-index:2;display:flex;flex-direction:column;align-items:center;gap:8px;padding:10px 0 6px}
.orb{width:110px;height:110px;position:relative;background:radial-gradient(circle at 32% 26%, #fff, #D8FBFF 12%, #5ED6FF 32%, #0A84FF 58%, #3A2AB8 82%, #08041A);border:1px solid rgba(255,255,255,.85);box-shadow:0 0 50px #0A84FF88,0 0 100px #BF5AF244;border-radius:50%}
.status{font-size:11px;letter-spacing:3.5px;color:#8BE9FF;font-weight:700}
.divider{position:relative;z-index:2;height:1px;margin:10px 28px 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.25),transparent)}
#chat{position:relative;z-index:2;flex:1;overflow-y:auto;padding:16px 28px;display:flex;flex-direction:column;gap:14px}
.row{display:flex;width:100%}.row.user{justify-content:flex-end}.row.bot{justify-content:flex-start}
.bubble{max-width:68%;padding:15px 18px 22px;border-radius:24px;position:relative;box-shadow:0 12px 32px rgba(0,0,0,.35);word-wrap:break-word;white-space:pre-wrap;line-height:1.5;font-size:15px}
.row.user .bubble{background:linear-gradient(135deg,rgba(46,160,255,.92),rgba(122,76,255,.92));border:1px solid rgba(255,255,255,.5)}
.row.bot .bubble{background:linear-gradient(135deg,rgba(42,53,79,.85),rgba(26,34,54,.85));border:1px solid rgba(255,255,255,.28)}
.bubble b{font-size:9px;letter-spacing:2px;opacity:.7;display:block;margin-bottom:5px}
.msg-time{position:absolute;bottom:6px;right:12px;font-size:10px;color:rgba(255,255,255,.55)}
.bubble img.genImg{width:100%;height:auto;display:block;border-radius:16px;margin-top:10px;cursor:zoom-in}
.copyBtn{position:absolute;top:8px;right:8px;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.35);color:white;font-size:11px;padding:5px 9px;border-radius:999px;cursor:pointer}
.limitBox{width:100%;aspect-ratio:1/1;max-width:420px;border-radius:16px;margin-top:10px;background:linear-gradient(135deg,#1a1a2e,#16213e);border:2px dashed rgba(255,255,255,.4);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-align:center;padding:20px}
.typing{display:flex;gap:6px;align-items:center;background:rgba(255,255,255,.15);padding:14px 18px;border-radius:22px;width:fit-content}
.dot{width:9px;height:9px;background:#7EDBFF;border-radius:50%;animation:dotBounce .55s ease-in-out infinite}.dot:nth-child(2){animation-delay:.12s}.dot:nth-child(3){animation-delay:.24s}
@keyframes dotBounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
.inputWrap{position:relative;z-index:2;padding:12px 28px 10px}
.pill{background:linear-gradient(135deg,rgba(255,255,255,.28),rgba(255,255,255,.08));backdrop-filter:blur(28px);border:1px solid rgba(255,255,255,.45);border-radius:32px;padding:10px 12px;display:flex;gap:12px;align-items:flex-end}
.pill textarea{flex:1;background:transparent;border:none;outline:none;color:white;font-size:16px;padding:10px;resize:none;min-height:44px;max-height:200px}
.pill textarea::placeholder{color:rgba(255,255,255,.6)}
.btn{width:62px;height:62px;min-width:62px;border-radius:32px;border:none;cursor:pointer;color:white;font-size:22px;font-weight:800;display:flex;align-items:center;justify-content:center}
.btn.blue{background:linear-gradient(135deg,#2EA0FF,#0A84FF 50%,#7A4CFF);border:1px solid rgba(255,255,255,.55)}
.btn.glass{background:linear-gradient(135deg,rgba(255,255,255,.38),rgba(255,255,255,.1));border:1px solid rgba(255,255,255,.55);font-size:28px}
footer{position:relative;z-index:2;text-align:center;padding:0 0 12px;font-size:9px;letter-spacing:2.6px;color:rgba(255,255,255,.35)}
#imgOverlay{position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.92);display:none;align-items:center;justify-content:center;flex-direction:column;gap:16px;padding:20px}
#imgOverlay.show{display:flex}#imgOverlay img{max-width:92vw;max-height:82vh;border-radius:20px}
#loginOverlay{position:fixed;inset:0;z-index:9999;background:#000;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;padding:20px}
#loginOverlay input{padding:14px;border-radius:14px;border:1px solid #333;background:#111;color:#fff;width:280px;font-size:16px}
#loginOverlay button{background:#00d4ff;border:none;padding:14px 20px;border-radius:14px;font-weight:800;width:280px;cursor:pointer;color:#000}
@media(max-width:800px){.sidebar{display:none}.bubble{max-width:88%}}
</style></head><body>
<div id="loginOverlay"><div style="font-size:32px;font-weight:800;letter-spacing:8px">J A R V I S</div><div style="color:#888;font-size:13px">Chacun son JARVIS perso</div><input id="loginPseudo" placeholder="Ton pseudo"><input id="loginCode" placeholder="Ton code secret" type="password"><button onclick="doLogin()">ENTRER DANS MON JARVIS</button><p id="loginErr" style="color:#ff5555;font-size:13px"></p></div>
<div class="bg" id="bg"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div></div>
<header><div><div class="logo">J A R V I S</div><div class="ver">9.4.5 • IMAGE FIX VRAI • SANS CROP • 120b</div></div><button class="clearBtn" onclick="clearAllMemory()">⌫  MÉMOIRE (TOUT SUPPRIMER)</button></header>
<div class="app"><div class="sidebar"><button class="newChatBtn" onclick="createNewChat()">➕  Nouveau Chat</button><h3>💬 TES CHATS • MEMOIRE GLOBALE</h3><div id="chatList" style="display:flex;flex-direction:column;gap:8px"></div><div style="margin-top:auto;padding:10px 8px;font-size:10px;color:rgba(255,255,255,.45);line-height:1.5">ℹ️ Chaque nouveau chat se souvient des autres chats.<br>Image : 1 toutes les 45s<br>Le bouton MÉMOIRE en haut supprime TOUT.</div></div>
<div class="main"><div class="orbWrap"><div class="orb" id="orb"></div><div class="status" id="status">●  SYSTEM ONLINE</div></div><div class="divider"></div><div id="chat"></div>
<div class="inputWrap"><div class="pill" id="pill"><button class="btn glass" onclick="document.getElementById('file').click()">+</button><textarea id="entry" rows="1" placeholder="Écris quelque chose à JARVIS... ou génère une image..."></textarea><button class="btn blue" onclick="send()">➤</button><input type="file" id="file" hidden onchange="onFile(this)" accept="image/*,.txt,.md,.pdf,.json,.csv,.docx,.py,.js,.html,.css"></div></div><footer>J A R V I S  9.4.5  •  IMAGE FIX VRAI  •  SANS CROP  •  LIQUID GLASS  •  GROQ AI</footer></div></div>
<div id="imgOverlay"><button style="position:absolute;top:18px;right:18px;width:52px;height:52px;border-radius:50%;background:#fff;color:#000;font-size:22px;cursor:pointer" onclick="closeFullscreen()">✕</button><img id="fullImg" src=""><div id="fullCaption">Clique sur ✕ pour fermer</div></div>
<script>
let USER=localStorage.getItem('jarvis_user')||'';let CODE=localStorage.getItem('jarvis_code')||'';
function doLogin(){let u=document.getElementById('loginPseudo').value.trim();let c=document.getElementById('loginCode').value.trim();if(!u||!c){document.getElementById('loginErr').innerText='Mets un pseudo + un code';return}localStorage.setItem('jarvis_user',u);localStorage.setItem('jarvis_code',c);USER=u;CODE=c;document.getElementById('loginOverlay').style.display='none';init();}
function authH(e){return Object.assign({'X-User':USER,'X-Code':CODE},e||{});}
if(USER&&CODE)document.getElementById('loginOverlay').style.display='none';
const chat=document.getElementById('chat');const entry=document.getElementById('entry');const statusEl=document.getElementById('status');
let currentChatId=null;let attached=null,attachedName="";
function onFile(inp){let f=inp.files[0];if(!f)return;attachedName=f.name;let r=new FileReader();r.onload=()=>{attached=r.result;};r.readAsDataURL(f);}
function openFullscreen(src,caption){let o=document.getElementById('imgOverlay');document.getElementById('fullImg').src=src;document.getElementById('fullCaption').textContent=caption||'Clique sur ✕ pour fermer';o.classList.add('show');}
function closeFullscreen(){document.getElementById('imgOverlay').classList.remove('show');document.getElementById('fullImg').src='';}
async function loadChats(){let r=await fetch('/chats',{headers:authH()});let list=await r.json();let el=document.getElementById('chatList');el.innerHTML='';list.forEach(c=>{let d=document.createElement('div');d.className='chatItem'+(c.id===currentChatId?' active':'');d.innerHTML=`<div class="t">${c.title}</div><div class="s">${c.count} msg • ${(c.last||'').slice(0,30)}</div><button class="del" onclick="event.stopPropagation();deleteChat(${c.id})">✕</button>`;d.onclick=()=>switchChat(c.id);el.appendChild(d);});}
async function createNewChat(){let r=await fetch('/chats/new',{method:'POST',headers:authH()});let data=await r.json();currentChatId=data.id;chat.innerHTML='';addMsg('Nouveau chat. Je me souviens des autres chats. Que puis-je faire ? 😎',false);await loadChats();}
async function switchChat(id){currentChatId=id;chat.innerHTML='';await loadChats();let r=await fetch('/history?chat_id='+id,{headers:authH()});let h=await r.json();if(h.length===0)addMsg('Nouveau chat. Je me souviens des autres chats aussi ✨',false);else h.forEach(m=>addMsg(m.content,m.role==='user'));}
async function deleteChat(id){if(!confirm('Supprimer ce chat ?'))return;await fetch('/chats/'+id+'/delete',{method:'POST',headers:authH()});await loadChats();let r=await fetch('/chats',{headers:authH()});let list=await r.json();if(list.length>0&&id===currentChatId)switchChat(list[0].id);}
async function clearAllMemory(){if(!confirm('Supprimer la mémoire de TOUS les chats ?'))return;let r=await fetch('/clear',{method:'POST',headers:authH()});let data=await r.json();currentChatId=data.new_chat_id;chat.innerHTML='';addMsg('Mémoire supprimée.',false);await loadChats();}
function renderTextWithImage(text,span){let mLimit=text.match(/\[LIMIT\](\d+)/);if(mLimit){span.textContent=text.replace(mLimit[0],'').trim();let box=document.createElement('div');box.className='limitBox';box.innerHTML=`<div>⏳</div><div>LIMITE FREE LIMIT</div><div>WAIT ${mLimit[1]}s</div>`;span.appendChild(box);return;}let m=text.match(/\[IMAGE\](https?:\/\/\S+)/);if(m){span.textContent=text.replace(m[0],'').trim();let img=document.createElement('img');img.src=m[1];img.className='genImg';img.onclick=()=>openFullscreen(m[1],text);span.appendChild(document.createElement('br'));span.appendChild(img);}else span.textContent=text;}
function addMsg(text,isUser){let row=document.createElement('div');row.className='row '+(isUser?'user':'bot');let b=document.createElement('div');b.className='bubble';let copyHtml=!isUser?`<button class="copyBtn" onclick="navigator.clipboard.writeText(this.parentElement.querySelector('span').innerText)">📋 Copier</button>`:"";b.innerHTML='<b>'+(isUser?'TOI':'JARVIS')+'</b><span></span>'+copyHtml+'<span class="msg-time">'+new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})+'</span>';row.appendChild(b);chat.appendChild(row);chat.scrollTop=chat.scrollHeight;let span=b.querySelector('span');if(text.includes('[IMAGE]')||text.includes('[LIMIT]'))renderTextWithImage(text,span);else span.textContent=text;}
let typingEl=null;function showTyping(){typingEl=document.createElement('div');typingEl.className='typing';typingEl.innerHTML='<div class="dot"></div><div class="dot"></div><div class="dot"></div>';chat.appendChild(typingEl);}function hideTyping(){if(typingEl)typingEl.remove();typingEl=null;}
async function send(){let q=entry.value.trim();if(!q&&!attached)return;if(!q)q="Décris cette image en détail.";let disp=q+(attachedName?'\n\n📎 '+attachedName:'');addMsg(disp,true);entry.value='';let fd=attached,fn=attachedName;attached=null;attachedName='';statusEl.textContent='●  PROCESSING';showTyping();try{let res=await fetch('/chat',{method:'POST',headers:authH({'Content-Type':'application/json'}),body:JSON.stringify({message:q,file:fd,fileName:fn,chat_id:currentChatId})});let data=await res.json();hideTyping();if(data.error)addMsg('Erreur :\n'+data.error,false);else addMsg(data.reply,false);await loadChats();}catch(e){hideTyping();addMsg('Erreur réseau : '+e,false);}statusEl.textContent='●  SYSTEM ONLINE';}
entry.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
async function init(){let r=await fetch('/chats',{headers:authH()});let list=await r.json();if(list.length>0)currentChatId=list[0].id;await loadChats();await switchChat(currentChatId);}
if(USER&&CODE)init();
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send_json(self, obj):
        data=json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        try:
            if self.path=='/' or self.path=='/index.html':
                data=HTML.encode('utf-8'); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
            if self.path=='/admin':
                data=ADMIN_HTML.encode('utf-8'); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
            if self.path=='/admin_data':
                if self.headers.get("X-Admin") != ADMIN_CODE:
                    self.send_json({"error":"Code admin faux"}); return
                out=[]
                for _n in load_users():
                    _m=get_mem(_n); _msgs=[]
                    for _c in _m.list_chats(): _msgs.extend(_m.load(_c["id"], 60))
                    out.append({"name":_n,"facts":_m.load_facts(),"messages":_msgs,"chats":_m.list_chats()})
                self.send_json({"users":out}); return
            _user = check_auth(self.headers)
            if _user is None or _user is False:
                self.send_json({"error":"Non autorise"}); return
            mem_u = get_mem(_user)
            if self.path=='/chats':
                self.send_json(mem_u.list_chats()); return
            elif self.path.startswith('/history'):
                from urllib.parse import urlparse, parse_qs
                qs=parse_qs(urlparse(self.path).query); cid=int(qs.get('chat_id',[1])[0])
                self.send_json(mem_u.load(cid,30)); return
            else: self.send_response(404); self.end_headers()
        except Exception as e: print("GET error", e); traceback.print_exc()
    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length',0) or 0)
            body=self.rfile.read(length) if length>0 else b'{}'
            try: payload=json.loads(body.decode('utf-8'))
            except: payload={}
            _user2 = check_auth(self.headers)
            if _user2 is None or _user2 is False:
                self.send_json({"error":"Pseudo ou code faux"}); return
            mem_u = get_mem(_user2)
            if self.path=='/clear':
                new_id=mem_u.clear_all(); self.send_json({"ok":True,"new_chat_id":new_id}); return
            if self.path=='/chats/new':
                nid=mem_u.create_chat(); self.send_json({"id":nid}); return
            if self.path.startswith('/chats/') and self.path.endswith('/rename'):
                try:
                    cid=int(self.path.split('/')[2]); new_title=(payload.get('title') or '').strip()[:35]
                    if new_title: mem_u.set_title(cid, force_french_title(new_title))
                    self.send_json({"ok":True,"title":new_title})
                except Exception as e: self.send_json({"ok":False,"error":str(e)})
                return
            if self.path.startswith('/chats/') and self.path.endswith('/delete'):
                try: cid=int(self.path.split('/')[2]); mem_u.delete_chat(cid)
                except: pass
                self.send_json({"ok":True}); return
            if self.path=='/chat':
                global LAST_IMAGE_TIME
                if client is None:
                    self.send_json({"error":"CLE MANQUANTE : mets ta vraie clé dans GROQ_API_KEY sur Render"}); return
                q=payload.get('message','') or 'Décris cette image.'
                file_data=payload.get('file'); file_name=payload.get('fileName','')
                chat_id=int(payload.get('chat_id') or 1)
                disp=q + (f"\n\n📎 {file_name}" if file_name else "")
                mem_u.save(chat_id, "user", disp)
                new_name, is_not_lenny = detect_name_change(q)
                if new_name:
                    mem_u.clear_name_facts(); mem_u.save_fact(f"Prénom utilisateur : {new_name}")
                elif is_not_lenny:
                    mem_u.clear_name_facts(); mem_u.save_fact("L'utilisateur n'est PAS Lenny, demande-lui son prénom et retiens-le")
                for f in extract_facts(q, chat_id):
                    if not f.startswith("Prénom utilisateur") and "PAS Lenny" not in f: mem_u.save_fact(f)
                current_name = mem_u.get_user_name()
                if is_image_request(q) and not file_data:
                    now = time.time(); elapsed = now - LAST_IMAGE_TIME
                    if LAST_IMAGE_TIME != 0 and elapsed < IMAGE_COOLDOWN:
                        wait = int(IMAGE_COOLDOWN - elapsed) + 1
                        ans = f"Trop vite ! Attends encore un peu 😅\n[LIMIT]{wait}"
                        mem_u.save(chat_id, "assistant", ans); self.send_json({"reply": ans}); return
                    LAST_IMAGE_TIME = now
                    prompt_clean = q
                    for w in ["génère une image de", "genere une image de", "crée une image de", "cree une image de", "fais une image de", "génère une image", "genere une image", "génère", "genere", "dessine", "crée une image", "cree une image", "une image de", "image de", "fais une image", "fait une image"]:
                        prompt_clean = prompt_clean.replace(w, "").replace(w.capitalize(), "")
                    prompt_clean = prompt_clean.strip(" :,.!") or "un paysage magnifique"
                    url = make_image_url(prompt_clean)
                    ans = f"Voilà ton image : {prompt_clean} 🔥\n[IMAGE]{url}"
                    mem_u.save(chat_id, "assistant", ans)
                    cur_title = mem_u.get_title(chat_id)
                    cnt = mem_u.c.execute("SELECT COUNT(*) FROM messages WHERE chat_id=?", (chat_id,)).fetchone()[0]
                    new_title = None; new_title_id = None
                    if cnt <= 2 or cur_title.startswith("Chat "):
                        new_title = generate_chat_title(prompt_clean); mem_u.set_title(chat_id, new_title); new_title_id = chat_id
                    self.send_json({"reply": ans, "new_title": new_title, "new_title_id": new_title_id}); return
                msgs = [{"role":"system","content": build_system_prompt(current_name or DEFAULT_NAME)}]
                facts = mem_u.load_facts()
                if facts: msgs.append({"role":"system","content":"Mémoire utilisateur : " + " | ".join(facts)})
                for m in mem_u.load_global(chat_id, 15): msgs.append(m)
                for m in mem_u.load(chat_id, 20)[:-1]: msgs.append(m)
                if file_data and file_data.startswith("data:image"):
                    try:
                        b64 = file_data.split(",",1)[1] if "," in file_data else file_data
                        msgs.append({"role":"user","content":[{"type":"text","text":q},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}]})
                        try:
                            c = client.chat.completions.create(model=VISION_MODELS[0], messages=msgs, temperature=0.7, max_completion_tokens=800)
                            ans = c.choices[0].message.content or "Pas de réponse."
                        except:
                            ans = call_groq([{"role":"system","content":build_system_prompt(current_name or DEFAULT_NAME)},{"role":"user","content":q+" [image jointe]"}], 800, current_name, mem_u)
                    except Exception as e: ans = f"Erreur fichier : {e}"
                else:
                    if file_data: msgs.append({"role":"user","content":q + f"\n\n[Fichier joint : {file_name}]"})
                    else: msgs.append({"role":"user","content":q})
                    ans = call_groq(msgs, 800, current_name, mem_u)
                mem_u.save(chat_id, "assistant", ans)
                cur_title = mem_u.get_title(chat_id)
                cnt = mem_u.c.execute("SELECT COUNT(*) FROM messages WHERE chat_id=?", (chat_id,)).fetchone()[0]
                new_title = None; new_title_id = None
                if cnt <= 2 or cur_title.startswith("Chat "):
                    new_title = generate_chat_title(q + " " + ans); mem_u.set_title(chat_id, new_title); new_title_id = chat_id
                self.send_json({"reply": ans, "new_title": new_title, "new_title_id": new_title_id}); return
            self.send_json({"error":"route inconnue"})
        except Exception as e:
            print("POST error", e); traceback.print_exc()
            try: self.send_json({"error": str(e)})
            except: pass

if __name__ == "__main__":
    print(f"JARVIS {VERSION} sur port {PORT} - GROQ: {'OK' if client else 'MANQUANTE'} - Admin: /admin")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
