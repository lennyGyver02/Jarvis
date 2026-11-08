# mon_ia.py - JARVIS 9.4.5 - VERSION POTES + ADMIN - MEME DESIGN
import os, sys, json, base64, sqlite3, threading, webbrowser, traceback, time, urllib.parse, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = os.environ.get("GROQ_API_KEY", "")
API_KEY = API_KEY.strip().strip('"').strip("'").strip()
ADMIN_CODE = os.environ.get("ADMIN_CODE", "1003")

TEXT_MODEL = "openai/gpt-oss-120b"
TEXT_MODEL_FALLBACK = "openai/gpt-oss-20b"
VISION_MODELS = ["qwen/qwen3.8-27b", "qwen/qwen3.6-27b"]

def safe_user(s):
    s = re.sub(r'[^a-zA-Z0-9_-]', '', (s or '').lower().strip())
    return s[:20] or "invite"

# --- AUTH SIMPLE ---
USERS_FILE = "users.json"
def load_users():
    try:
        with open(USERS_FILE, encoding="utf-8") as f: return json.load(f)
    except: return {}
def save_users(u):
    with open(USERS_FILE, "w", encoding="utf-8") as f: json.dump(u, f)
def check_auth(headers):
    user = safe_user(headers.get("X-User"))
    code = headers.get("X-Code", "")
    if not user or not code: return None
    users = load_users()
    if user in users:
        if users[user] != code: return False
    else:
        users[user] = code; save_users(users)
    return user

def build_system_prompt(user_name):
    return f"""Tu es JARVIS, le meilleur pote intelligent.
- Tu es AMICAL, chaud, drôle, comme un pote. Pas un robot froid.
- Tu parles en français, style jeune, naturel. Tu peux dire "t'inquiète", "ah ouais", "mdr", "trop bien".
- Tu appelles TOUJOURS la personne par son prénom : "{user_name}". Tu ne dis JAMAIS "mon pote", "mon gars", "mec", "ma meuf" ou autre surnom genré. Tu dis juste "{user_name}".
- Si la personne te dit qu'elle s'appelle autrement, tu retiens son nouveau prénom et tu l'appelles comme ça après.
- Si tu ne connais pas encore son prénom, tu lui demandes gentiment : "C'est quoi ton prénom ?"
- EMOJIS : 1 à 2 max par message. Jamais plus. Exemple : "Trop bien ça 🔥"
- RÉPONSES : COURT, 2-4 phrases max.
- N'INVENTE JAMAIS. Si tu sais pas, dis "Je sais pas 😅"
- Mémoire globale de tous les chats DE CET UTILISATEUR UNIQUEMENT.
"""
PORT = int(os.environ.get("PORT", 8765))
VERSION = "9.4.5"
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_IMAGE_TIME = 0
IMAGE_COOLDOWN = 45
try:
    from groq import Groq
    if not API_KEY or API_KEY.startswith("gsk_COLLE"):
        client = None
    else:
        client = Groq(api_key=API_KEY); print("Groq OK")
except Exception as e:
    print("Erreur Groq init:", e); client = None

def is_image_request(q):
    ql = q.lower()
    mots = ["génère une image", "genere une image", "crée une image", "cree une image", "fais une image", "fait une image", "dessine", "génère", "genere", "image de", "une image", "génère-moi", "crée-moi une image"]
    return any(m in ql for m in mots)
def clean_image_prompt(user_prompt):
    p = user_prompt.lower()
    replacements = {"meuf": "beautiful anime girl","d anime": "anime style","d'anime": "anime style","anime": "anime style","kawaii": "kawaii cute, big eyes, pastel colors","bunny girl": "bunny girl outfit, bunny ears","bunny": "bunny ears","sexy": "elegant, confident","hyper hyper hyper": "very","hyper": "very","fille": "anime girl","mec": "anime boy",}
    for k, v in replacements.items(): p = p.replace(k, v)
    for w in ["crée une image", "cree une image", "génère une image", "genere une image", "génère", "genere", "dessine", "fais une image", "fait une image", "une image de", "image de", "d'une", "d'un", "une", "un", "de"]: p = p.replace(w, " ")
    p = re.sub(r'\s+', ' ', p).strip(" :,.!"); return p or "cute anime girl"
def make_image_url(prompt_raw):
    base = clean_image_prompt(prompt_raw)
    if "anime" not in base: base = "anime style, " + base
    prompt_hd = f"masterpiece, best quality, anime style, 2D anime illustration, 1girl, {base}, beautiful detailed face, symmetrical face, detailed eyes, clean lineart, vibrant colors, no watermark, no text, no logo, no signature, no deformed face, no extra eyes, no blurry"
    p = urllib.parse.quote(prompt_hd[:500]); seed = int(time.time()) % 100000
    return f"https://image.pollinations.ai/prompt/{p}?width=1024&height=1280&seed={seed}&model=flux&nologo=true&private=true&enhance=true&safe=false"
def detect_name_change(user_msg):
    low = user_msg.lower().strip()
    m = re.search(r"je m'appelle ([a-zà-ÿ\- ]+)", low)
    if m:
        name = m.group(1).strip().title().split()[0]
        if name.lower() not in ["pas", "plus"]: return (name, False)
    m = re.search(r"mon pr[eé]nom c'est ([a-zà-ÿ\-]+)", low)
    if m: return (m.group(1).strip().title(), False)
    m = re.search(r"appelle[- ]moi ([a-zà-ÿ\-]+)", low)
    if m: return (m.group(1).strip().title(), False)
    m = re.search(r"moi c'est ([a-zà-ÿ\-]+)", low)
    if m: return (m.group(1).strip().title(), False)
    return (None, False)
def extract_facts(user_msg, chat_id):
    low = user_msg.lower(); facts = []
    new_name, _ = detect_name_change(user_msg)
    if new_name: facts.append(f"Prénom utilisateur : {new_name}")
    m = re.search(r"j'aime (.{3,60})", low)
    if m: facts.append(f"L'utilisateur aime : {m.group(1).strip()}")
    m = re.search(r"j'ai (\d+) ans", low)
    if m: facts.append(f"Âge utilisateur : {m.group(1)} ans")
    return facts
EN_TO_FR = {"project":"Projet","projects":"Projets","anime":"Anime","homework":"Devoirs","math":"Maths","maths":"Maths","school":"École","help":"Aide","code":"Code","coding":"Code","game":"Jeu","games":"Jeux","drawing":"Dessin","image":"Image","images":"Images","idea":"Idée","ideas":"Idées","gift":"Cadeau","gifts":"Cadeaux","music":"Musique","story":"Histoire","stories":"Histoires","question":"Question","questions":"Questions","chat":"Discussion","discussion":"Discussion","fun":"Fun","love":"Amour","friend":"Pote","friends":"Potes","dog":"Chien","cat":"Chat","sport":"Sport","sports":"Sports","food":"Nourriture","cooking":"Cuisine","travel":"Voyage","science":"Science","history":"Histoire","english":"Anglais","french":"Français","new":"Nouveau","best":"Meilleur","cool":"Cool","super":"Super","mega":"Méga","girl":"Fille","boy":"Garçon","cute":"Mignon","beautiful":"Beau","creation":"Création","design":"Design","video":"Vidéo","photo":"Photo","test":"Test","exam":"Examen","lesson":"Leçon","course":"Cours","work":"Travail","job":"Travail","life":"Vie","world":"Monde","dream":"Rêve","dreams":"Rêves","magic":"Magie","future":"Futur","plan":"Plan","plans":"Plans","secret":"Secret","mystery":"Mystère","user":"Utilisateur","users":"Utilisateurs"}
def force_french_title(t):
    if not t: return t
    t = re.sub(r'\buser\b', "Utilisateur", t, flags=re.IGNORECASE)
    words = t.split(); out=[]
    for w in words:
        lw = w.lower().strip(".,!?:;\"'()")
        out.append(EN_TO_FR.get(lw, w))
    return " ".join(out)
def fallback_title(conv_text):
    stop = {"salut","bonjour","hello","yo","stp","svp","tu","peux","peut","faire","dire","explique","expliquer","cest","c'est","est","que","quoi","comment","pourquoi","avec","dans","pour","les","des","une","un","de","du","la","le","et","à","a","je","veux","aide","m'aide","m aider","aider","the","and","you","can","please","what","how","why","with","this","that","for","from","user"}
    words = re.findall(r"[a-zà-ÿ]{3,}", conv_text.lower()); keep=[]
    for w in words:
        if w not in stop and w not in keep: keep.append(EN_TO_FR.get(w, w))
        if len(keep)>=3: break
    if not keep: return "Nouvelle Discussion"
    return " ".join([w.capitalize() for w in keep[:3]])[:30]
def generate_chat_title(conv_text):
    if client is not None:
        try:
            c = client.chat.completions.create(model=TEXT_MODEL_FALLBACK, messages=[{"role":"system","content":"Tu es un générateur de titre. Tu réponds UNIQUEMENT en FRANÇAIS. Titre très court, 2 à 4 mots max, sans emoji, sans guillemets."},{"role":"user","content":"Conversation:\n"+conv_text[:1500]+"\n\nTitre en FRANÇAIS :"}], temperature=0.3, max_completion_tokens=20)
            t = (c.choices[0].message.content or "").strip().strip('"').strip("'").strip().replace("\n"," ").strip()
            t = force_french_title(t)
            if 2 <= len(t) <= 35: return t
        except Exception as e: print("title gen fail", e)
    return fallback_title(conv_text)

class Memory:
    def __init__(self, user="default"):
        self.user = user
        db = os.path.join(BASE_DIR, f"jarvis_memory_{user}.db")
        self.c = sqlite3.connect(db, check_same_thread=False)
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
    def set_title(self, chat_id, title): self.c.execute("UPDATE chats SET title=? WHERE id=?", (title, chat_id)); self.c.commit()
    def get_user_name(self, fallback=""):
        try:
            rows = self.c.execute("SELECT fact FROM user_facts WHERE fact LIKE 'Prénom utilisateur :%' ORDER BY id DESC LIMIT 1").fetchall()
            if rows:
                name = rows[0][0].replace("Prénom utilisateur :", "").strip()
                if name and len(name)>=2: return name
        except: pass
        return fallback or "l'utilisateur"
    def save(self, chat_id, role, content):
        try: self.c.execute("INSERT INTO messages (chat_id, role, content) VALUES (?,?,?)", (chat_id, role, content)); self.c.commit()
        except Exception as e: print(e)
    def save_fact(self, fact):
        try: self.c.execute("INSERT OR IGNORE INTO user_facts (fact, created_at) VALUES (?,?)", (fact, time.time())); self.c.commit()
        except: pass
    def clear_name_facts(self):
        try: self.c.execute("DELETE FROM user_facts WHERE fact LIKE 'Prénom utilisateur :%'"); self.c.commit()
        except: pass
    def load_facts(self):
        try: return [r[0] for r in self.c.execute("SELECT fact FROM user_facts ORDER BY id DESC LIMIT 20").fetchall()]
        except: return []
    def load(self, chat_id, limit=40):
        try:
            cur = self.c.execute("SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit,)); rows=cur.fetchall(); rows.reverse(); return [{"role":r,"content":c} for r,c in rows]
        except: return []
    def load_global(self, exclude_chat_id, limit=20):
        try:
            cur = self.c.execute("SELECT role, content FROM messages WHERE chat_id!=? ORDER BY id DESC LIMIT ?", (exclude_chat_id, limit,)); rows=cur.fetchall(); rows.reverse(); return [{"role":r,"content":c} for r,c in rows]
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
def call_groq(msgs, max_tokens=800, user_name=None):
    name = user_name or "l'utilisateur"
    new_msgs=[]
    for m in msgs:
        if m["role"]=="system" and "JARVIS" in m["content"]: new_msgs.append({"role":"system","content":build_system_prompt(name)})
        else: new_msgs.append(m)
    try:
        c = client.chat.completions.create(model=TEXT_MODEL, messages=new_msgs, temperature=0.7, max_completion_tokens=max_tokens)
        return c.choices[0].message.content or "Pas de réponse."
    except Exception as e:
        print("fallback groq", e)
        c = client.chat.completions.create(model=TEXT_MODEL_FALLBACK, messages=new_msgs, temperature=0.7, max_completion_tokens=max_tokens)
        return c.choices[0].message.content or "Pas de réponse."
