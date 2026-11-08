# mon_ia.py - JARVIS FINAL - VERSION EN LIGNE + LENNY + TITRE FRANCAIS
import os, sys, json, base64, sqlite3, threading, webbrowser, traceback, time, urllib.parse, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# CLE : en local tu mets ta clé ici, sur Render tu mets GROQ_API_KEY dans les variables d'environnement
API_KEY = os.environ.get("GROQ_API_KEY", "")
API_KEY = API_KEY.strip().strip('"').strip("'").strip()
ADMIN_CODE = os.environ.get("ADMIN_CODE", "TON_CODE_ADMIN_ICI")
def safe_user(s):
    import re
    s = re.sub(r'[^a-zA-Z0-9_-]', '', (s or '').lower().strip())
    return s[:20] or "invite"
def load_users():
    try:
        with open("users.json", encoding="utf-8") as f: return json.load(f)
    except: return {}
def save_users(u):
    with open("users.json", "w", encoding="utf-8") as f: json.dump(u, f)
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
MEMS = {}
def get_mem(user):
    if user not in MEMS: MEMS[user] = Memory(user)
    return MEMS[user]
TEXT_MODEL = "openai/gpt-oss-120b"
TEXT_MODEL_FALLBACK = "openai/gpt-oss-20b"
VISION_MODELS = ["qwen/qwen3.8-27b", "qwen/qwen3.6-27b"]

DEFAULT_NAME = "Lenny"

def build_system_prompt(user_name):
    return f"""Tu es JARVIS, le meilleur pote intelligent.
- Tu es AMICAL, chaud, drôle, comme un pote. Pas un robot froid.
- Tu parles en français, style jeune, naturel. Tu peux dire "t'inquiète", "ah ouais", "mdr", "trop bien".
- Tu appelles TOUJOURS la personne par son prénom : "{user_name}". Tu ne dis JAMAIS "mon pote", "mon gars", "mec", "ma meuf" ou autre surnom genré. Tu dis juste "{user_name}".
- Si la personne te dit qu'elle ne s'appelle pas {user_name} ou qu'elle s'appelle autrement, tu retiens son nouveau prénom et tu l'appelles comme ça après. Tu ne redis plus {user_name}.
- Si tu ne connais pas encore son prénom, tu lui demandes gentiment : "C'est quoi ton prénom ?"
- EMOJIS : 1 à 2 max par message. Jamais plus. Exemple : "Trop bien ça 🔥"
- RÉPONSES : COURT, 2-4 phrases max.
- N'INVENTE JAMAIS. Si tu sais pas, dis "Je sais pas 😅"
- Mémoire globale de tous les chats.
"""

SYSTEM_PROMPT = build_system_prompt(DEFAULT_NAME)

PORT = int(os.environ.get("PORT", 8765))
VERSION = "9.4.5"

# CHEMIN BASE : marche en .py, en .exe, et en ligne sur Render
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "jarvis_memory.db")
LAST_IMAGE_TIME = 0
IMAGE_COOLDOWN = 45

try:
    from groq import Groq
    if not API_KEY or API_KEY.startswith("gsk_COLLE") or API_KEY == "gsk_TA_CLE_ICI":
        client = None
    else:
        client = Groq(api_key=API_KEY)
        print("Groq OK")
except Exception as e:
    print("Erreur Groq init:", e); client = None

def is_image_request(q):
    ql = q.lower()
    mots = ["génère une image", "genere une image", "crée une image", "cree une image", "fais une image", "fait une image", "dessine", "génère", "genere", "image de", "une image", "génère-moi", "crée-moi une image"]
    return any(m in ql for m in mots)

def clean_image_prompt(user_prompt):
    p = user_prompt.lower()
    replacements = {"meuf": "beautiful anime girl","d anime": "anime style","d'anime": "anime style","anime": "anime style","kawaii": "kawaii cute, big eyes, pastel colors","bunny girl": "bunny girl outfit, bunny ears","bunny": "bunny ears","sexy": "elegant, confident","hyper hyper hyper": "very","hyper": "very","fille": "anime girl","mec": "anime boy",}
    for k, v in replacements.items():
        p = p.replace(k, v)
    for w in ["crée une image", "cree une image", "génère une image", "genere une image", "génère", "genere", "dessine", "fais une image", "fait une image", "une image de", "image de", "d'une", "d'un", "une", "un", "de"]:
        p = p.replace(w, " ")
    p = re.sub(r'\s+', ' ', p).strip(" :,.!")
    return p or "cute anime girl"

def make_image_url(prompt_raw):
    base = clean_image_prompt(prompt_raw)
    if "anime" not in base:
        base = "anime style, " + base
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
                if cand.lower() not in ["pas", "lenny"] and len(cand) >= 2:
                    return (cand.strip().title(), False)
            if name.lower() == "lenny":
                return (DEFAULT_NAME, False)
            if "pas" in low and "lenny" in low and len(all_names) == 1:
                return (None, True)
            return (name, False)
    m = re.search(r"mon pr[eé]nom c'est ([a-zà-ÿ\-]+)", low)
    if m:
        return (m.group(1).strip().title(), False)
    m = re.search(r"mon prénom est ([a-zà-ÿ\-]+)", low)
    if m:
        return (m.group(1).strip().title(), False)
    m = re.search(r"appelle[- ]moi ([a-zà-ÿ\-]+)", low)
    if m:
        return (m.group(1).strip().title(), False)
    if re.search(r"(je (ne )?suis pas|je suis pas|c'est pas|ce n'est pas|chuis pas)\s+lenny", low):
        return (None, True)
    m = re.search(r"je suis ([a-zà-ÿ\-]+)", low)
    if m:
        cand = m.group(1).strip().title()
        if cand.lower() not in ["pas", "plus", "lenny", "là", "la", "ici", "fatigué", "fatiguée", "content", "contente", "triste", "ok", "bien"]:
            return (cand, False)
    m = re.search(r"moi c'est ([a-zà-ÿ\-]+)", low)
    if m:
        return (m.group(1).strip().title(), False)
    return (None, False)

def extract_facts(user_msg, chat_id):
    low = user_msg.lower()
    facts = []
    new_name, is_not_lenny = detect_name_change(user_msg)
    if new_name:
        facts.append(f"Prénom utilisateur : {new_name}")
    if is_not_lenny:
        facts.append("L'utilisateur n'est PAS Lenny, demande-lui son prénom et retiens-le")
    m = re.search(r"j'aime (.{3,60})", low)
    if m: facts.append(f"L'utilisateur aime : {m.group(1).strip()}")
    m = re.search(r"j'ai (\d+) ans", low)
    if m: facts.append(f"Âge utilisateur : {m.group(1)} ans")
    return facts

EN_TO_FR = {
    "project": "Projet", "projects": "Projets", "anime": "Anime", "homework": "Devoirs", "math": "Maths", "maths": "Maths",
    "school": "École", "help": "Aide", "code": "Code", "coding": "Code", "game": "Jeu", "games": "Jeux",
    "drawing": "Dessin", "image": "Image", "images": "Images", "idea": "Idée", "ideas": "Idées",
    "gift": "Cadeau", "gifts": "Cadeaux", "music": "Musique", "story": "Histoire", "stories": "Histoires",
    "question": "Question", "questions": "Questions", "chat": "Discussion", "discussion": "Discussion",
    "fun": "Fun", "love": "Amour", "friend": "Pote", "friends": "Potes", "dog": "Chien", "cat": "Chat",
    "sport": "Sport", "sports": "Sports", "food": "Nourriture", "cooking": "Cuisine", "travel": "Voyage",
    "science": "Science", "history": "Histoire", "english": "Anglais", "french": "Français",
    "new": "Nouveau", "best": "Meilleur", "cool": "Cool", "super": "Super", "mega": "Méga",
    "girl": "Fille", "boy": "Garçon", "cute": "Mignon", "beautiful": "Beau",
    "creation": "Création", "design": "Design", "video": "Vidéo", "photo": "Photo",
    "test": "Test", "exam": "Examen", "lesson": "Leçon", "course": "Cours",
    "work": "Travail", "job": "Travail", "life": "Vie", "world": "Monde",
    "dream": "Rêve", "dreams": "Rêves", "magic": "Magie", "future": "Futur",
    "plan": "Plan", "plans": "Plans", "secret": "Secret", "mystery": "Mystère",
    "user": "Utilisateur", "users": "Utilisateurs"
}

def force_french_title(t):
    if not t:
        return t
    t = re.sub(r'\buser\b', "Utilisateur", t, flags=re.IGNORECASE)
    t = re.sub(r'\busers\b', "Utilisateurs", t, flags=re.IGNORECASE)
    words = t.split()
    out = []
    for w in words:
        lw = w.lower().strip(".,!?:;\"'()")
        if lw in EN_TO_FR:
            out.append(EN_TO_FR[lw])
        else:
            out.append(w)
    return " ".join(out)

def fallback_title(conv_text):
    stop = {"salut","bonjour","hello","yo","stp","svp","tu","peux","peut","faire","dire","explique","expliquer","cest","c'est","est","que","quoi","comment","pourquoi","avec","dans","pour","les","des","une","un","de","du","la","le","et","à","a","je","veux","aide","m'aide","m aider","aider","the","and","you","can","please","what","how","why","with","this","that","for","from","user"}
    words = re.findall(r"[a-zà-ÿ]{3,}", conv_text.lower())
    keep = []
    for w in words:
        if w not in stop and w not in keep:
            fr = EN_TO_FR.get(w, w)
            keep.append(fr)
        if len(keep) >= 3:
            break
    if not keep:
        return "Nouvelle Discussion"
    return " ".join([w.capitalize() for w in keep[:3]])[:30]

def generate_chat_title(conv_text):
    if client is not None:
        try:
            c = client.chat.completions.create(model=TEXT_MODEL_FALLBACK, messages=[{"role":"system","content":"Tu es un générateur de titre. Tu réponds UNIQUEMENT en FRANÇAIS. JAMAIS en anglais. JAMAIS de mot anglais. JAMAIS le mot 'user', tu dis 'Utilisateur' à la place. Tu crées un titre de chat très court, 2 à 4 mots max, en français, sans emoji, sans guillemets, sans point. Exemples en FRANÇAIS : Projet Anime, Devoirs Maths, Idée Cadeau, Aide Code, Discussion Fun, Histoire Magique. Si la conversation est en anglais, tu TRADUIS le titre en français. Réponds UNIQUEMENT le titre en français."},{"role":"user","content":"Conversation:\n"+conv_text[:1500]+"\n\nTitre en FRANÇAIS uniquement :"}], temperature=0.3, max_completion_tokens=20)
            t = (c.choices[0].message.content or "").strip().strip('"').strip("'").strip()
            t = t.replace("\n"," ").strip()
            t = force_french_title(t)
            if 2 <= len(t) <= 35:
                return t
        except Exception as e:
            print("title gen fail", e)
    return fallback_title(conv_text)

class Memory:
    def __init__(self):
        self.c = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.c.execute("CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_at REAL)")
        self.c.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, role TEXT, content TEXT)")
        self.c.execute("CREATE TABLE IF NOT EXISTS user_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, fact TEXT UNIQUE, created_at REAL)")
        try:
            cols = [r[1] for r in self.c.execute("PRAGMA table_info(messages)")]
            if "chat_id" not in cols:
                self.c.execute("ALTER TABLE messages ADD COLUMN chat_id INTEGER DEFAULT 1")
        except: pass
        self.c.commit()
        if self.c.execute("SELECT COUNT(*) FROM chats").fetchone()[0]==0:
            self.c.execute("INSERT INTO chats (title, created_at) VALUES (?,?)", ("Chat 1", time.time())); self.c.commit()
        try: self.c.execute("UPDATE messages SET chat_id=1 WHERE chat_id IS NULL"); self.c.commit()
        except: pass
    def list_chats(self):
        rows = self.c.execute("SELECT id, title, created_at FROM chats ORDER BY id DESC").fetchall()
        out=[]
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
        r = self.c.execute("SELECT title FROM chats WHERE id=?", (chat_id,)).fetchone()
        return r[0] if r else ""
    def set_title(self, chat_id, title):
        self.c.execute("UPDATE chats SET title=? WHERE id=?", (title, chat_id)); self.c.commit()
    def get_user_name(self):
        try:
            rows = self.c.execute("SELECT fact FROM user_facts WHERE fact LIKE 'Prénom utilisateur :%' ORDER BY id DESC LIMIT 1").fetchall()
            if rows:
                name = rows[0][0].replace("Prénom utilisateur :", "").strip()
                if name and len(name) >= 2:
                    return name
            not_lenny = self.c.execute("SELECT COUNT(*) FROM user_facts WHERE fact LIKE '%PAS Lenny%'").fetchone()[0]
            if not_lenny > 0:
                return None
        except: pass
        return DEFAULT_NAME
    def save(self, chat_id, role, content):
        try: self.c.execute("INSERT INTO messages (chat_id, role, content) VALUES (?,?,?)", (chat_id, role, content)); self.c.commit()
        except Exception as e: print(e)
    def save_fact(self, fact):
        try: self.c.execute("INSERT OR IGNORE INTO user_facts (fact, created_at) VALUES (?,?)", (fact, time.time())); self.c.commit()
        except: pass
    def clear_name_facts(self):
        try:
            self.c.execute("DELETE FROM user_facts WHERE fact LIKE 'Prénom utilisateur :%' OR fact LIKE '%PAS Lenny%'"); self.c.commit()
        except: pass
    def load_facts(self):
        try:
            rows = self.c.execute("SELECT fact FROM user_facts ORDER BY id DESC LIMIT 20").fetchall()
            return [r[0] for r in rows]
        except: return []
    def load(self, chat_id, limit=40):
        try:
            cur = self.c.execute("SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit,))
            rows = cur.fetchall(); rows.reverse(); return [{"role": r, "content": c} for r, c in rows]
        except: return []
    def load_global(self, exclude_chat_id, limit=20):
        try:
            cur = self.c.execute("SELECT role, content FROM messages WHERE chat_id!=? ORDER BY id DESC LIMIT ?", (exclude_chat_id, limit,))
            rows = cur.fetchall(); rows.reverse(); return [{"role": r, "content": c} for r, c in rows]
        except: return []
    def delete_chat(self, chat_id):
        self.c.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,)); self.c.execute("DELETE FROM chats WHERE id=?", (chat_id,)); self.c.commit()
        if self.c.execute("SELECT COUNT(*) FROM chats").fetchone()[0]==0:
            self.c.execute("INSERT INTO chats (title, created_at) VALUES (?,?)", ("Chat 1", time.time())); self.c.commit()
    def clear_all(self):
        self.c.execute("DELETE FROM messages"); self.c.execute("DELETE FROM chats"); self.c.execute("DELETE FROM user_facts"); self.c.commit()
        self.c.execute("INSERT INTO chats (title, created_at) VALUES (?,?)", ("Chat 1", time.time())); self.c.commit()
        return self.c.execute("SELECT MAX(id) FROM chats").fetchone()[0]
mem = Memory()

def call_groq(msgs, max_tokens=800, user_name=None):
    name = user_name or mem.get_user_name() or DEFAULT_NAME
    new_msgs = []
    for m in msgs:
        if m["role"] == "system" and "JARVIS" in m["content"]:
            new_msgs.append({"role":"system","content": build_system_prompt(name if name else "l'utilisateur")})
        else:
            new_msgs.append(m)
    try:
        c = client.chat.completions.create(model=TEXT_MODEL, messages=new_msgs, temperature=0.7, max_completion_tokens=max_tokens)
        return c.choices[0].message.content or "Pas de réponse."
    except Exception as e:
        c = client.chat.completions.create(model=TEXT_MODEL_FALLBACK, messages=new_msgs, temperature=0.7, max_completion_tokens=max_tokens)
        return c.choices[0].message.content or "Pas de réponse."

HTML = r"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>JARVIS 9.4.5</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",Inter,sans-serif}
body{height:100vh;overflow:hidden;background:#000;color:white;display:flex;flex-direction:column}
body.shake{animation:shakeStylish .55s cubic-bezier(.36,.07,.19,.97) both}
@keyframes shakeStylish{10%,90%{transform:translate(-2px,1px) rotate(-.2deg)}20%,80%{transform:translate(3px,-2px) rotate(.3deg)}30%,50%,70%{transform:translate(-5px,2px) rotate(-.4deg)}40%,60%{transform:translate(5px,-2px) rotate(.4deg)}}
body.jump{animation:jumpAnim .5s cubic-bezier(.34,1.56,.64,1)}
@keyframes jumpAnim{0%{transform:translateY(0)}40%{transform:translateY(-8px) scale(1.004)}70%{transform:translateY(3px)}100%{transform:translateY(0)}}
.trail{position:fixed;width:10px;height:10px;border-radius:50%;pointer-events:none;z-index:999;will-change:transform,opacity;animation:trailFade .65s ease-out forwards}
@keyframes trailFade{0%{transform:scale(1);opacity:.9}100%{transform:scale(0) translateY(10px);opacity:0}}
.ripple{position:fixed;border:2px solid rgba(255,255,255,.7);border-radius:50%;pointer-events:none;z-index:998;animation:rippleAnim .8s cubic-bezier(.2,.8,.2,1) forwards}
@keyframes rippleAnim{0%{width:0;height:0;opacity:1;transform:translate(-50%,-50%)}100%{width:220px;height:220px;opacity:0;transform:translate(-50%,-50%)}}
.bg{position:fixed;inset:-40px;z-index:0;background:radial-gradient(700px 500px at 15% 15%, #0A84FF2E, transparent),radial-gradient(700px 500px at 85% 85%, #BF5AF22A, transparent),linear-gradient(180deg,#000,#050814 50%,#0A0B22);overflow:hidden;transition:transform .3s cubic-bezier(.2,.8,.2,1)}
.bg.shakeBg{animation:bgShake .55s ease-in-out}
@keyframes bgShake{0%,100%{filter:brightness(1)}25%{filter:brightness(1.25)}50%{filter:brightness(.9)}75%{filter:brightness(1.2)}}
.blob{position:absolute;border-radius:50%;filter:blur(70px);opacity:.55;animation:blobFloat 9s ease-in-out infinite alternate, blobMorph 11s ease-in-out infinite alternate}
.b1{width:480px;height:480px;background:#0A84FF;top:-80px;left:-80px}
.b2{width:420px;height:420px;background:#BF5AF2;bottom:-80px;right:-60px;animation-delay:-4s}
.b3{width:320px;height:320px;background:#00D2FF;top:60%;left:35%;animation-delay:-2s;opacity:.35}
@keyframes blobFloat{from{transform:translate(0,0) scale(1)}to{transform:translate(70px,45px) scale(1.15)}}
@keyframes blobMorph{0%,100%{border-radius:50%}25%{border-radius:58% 42% 55% 45% / 48% 55% 45% 52%}50%{border-radius:45% 55% 48% 52% / 58% 42% 55% 45%}75%{border-radius:52% 48% 42% 58% / 45% 55% 48% 52%}}
.star{position:absolute;color:#fff;font-size:9px;animation:twinkle 2.5s ease-in-out infinite}
@keyframes twinkle{0%,100%{opacity:.25}50%{opacity:.95}}
.particle{position:fixed;width:8px;height:8px;border-radius:50%;pointer-events:none;z-index:100;animation:particleFly 1s cubic-bezier(.2,.8,.2,1) forwards}
@keyframes particleFly{0%{transform:translate(0,0) scale(1) rotate(0);opacity:1}100%{transform:translate(var(--dx),var(--dy)) scale(0) rotate(720deg);opacity:0}}
.app{position:relative;z-index:2;flex:1;display:flex;min-height:0}
.sidebar{width:260px;min-width:260px;display:flex;flex-direction:column;gap:10px;padding:14px 12px;background:linear-gradient(180deg,rgba(255,255,255,.14),rgba(255,255,255,.05));backdrop-filter:blur(28px) saturate(180%);border-right:1px solid rgba(255,255,255,.22);box-shadow:8px 0 32px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.4);overflow-y:auto}
.sidebar h3{font-size:10px;letter-spacing:3px;color:rgba(255,255,255,.6);padding:2px 8px}
.newChatBtn{width:100%;padding:13px;border-radius:18px;border:1px solid rgba(255,255,255,.55);background:linear-gradient(135deg,#2EA0FF,#7A4CFF);color:white;font-size:14px;font-weight:800;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;box-shadow:0 10px 28px rgba(10,132,255,.4), inset 0 1px 0 rgba(255,255,255,.6);transition:transform .22s cubic-bezier(.34,1.56,.64,1);position:relative;overflow:hidden}
.newChatBtn:hover{transform:scale(1.03) rotate(-.5deg)}
.newChatBtn:active{transform:scale(.96)}
.newChatBtn::after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 30%,rgba(255,255,255,.4) 50%,transparent 70%);transform:translateX(-120%);transition:transform .6s}
.newChatBtn:hover::after{transform:translateX(120%)}
.chatItem{padding:12px 12px;border-radius:16px;cursor:pointer;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);transition:all .22s cubic-bezier(.34,1.56,.64,1);position:relative;overflow:hidden;padding-right:62px}
.chatItem:hover{transform:scale(1.02) translateX(3px);background:rgba(255,255,255,.14)}
.chatItem.active{background:linear-gradient(135deg,rgba(46,160,255,.35),rgba(122,76,255,.35));border-color:rgba(255,255,255,.5);box-shadow:0 8px 24px rgba(10,132,255,.25), inset 0 1px 0 rgba(255,255,255,.5);transform:scale(1.02)}
.chatItem .t{font-size:14px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chatItem .t .titleText{display:flex;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chatItem .s{font-size:11px;color:rgba(255,255,255,.55);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
.chatItem .del{position:absolute;top:8px;right:8px;background:rgba(255,55,95,.85);border:none;color:white;width:22px;height:22px;border-radius:50%;font-size:11px;cursor:pointer;display:none;align-items:center;justify-content:center;z-index:3}
.chatItem:hover .del{display:flex}
.chatItem.anim-in{animation:popClean .45s cubic-bezier(.34,1.56,.64,1) both}
.chatTitleLetter{display:inline-block;animation:titleLetterIn .55s cubic-bezier(.34,1.56,.64,1) both;will-change:transform,opacity}
@keyframes titleLetterIn{0%{transform:translateY(-14px) scale(.7) rotate(-4deg);opacity:0;filter:blur(2px)}55%{transform:translateY(2px) scale(1.12) rotate(1deg);opacity:1;filter:blur(0)}100%{transform:translateY(0) scale(1) rotate(0);opacity:1;filter:blur(0)}}
.editTitleBtn{position:absolute;top:8px;right:34px;width:22px;height:22px;border-radius:50%;border:1px solid rgba(255,255,255,.4);background:linear-gradient(135deg,rgba(255,255,255,.25),rgba(10,132,255,.35));backdrop-filter:blur(10px);color:white;font-size:11px;cursor:pointer;display:none;align-items:center;justify-content:center;transition:transform .22s cubic-bezier(.34,1.56,.64,1), box-shadow .22s, background .22s;box-shadow:0 4px 12px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.6);z-index:3}
.chatItem:hover .editTitleBtn{display:flex}
.editTitleBtn:hover{transform:scale(1.25) rotate(12deg);box-shadow:0 0 16px #0A84FF88,0 0 24px #BF5AF266;background:linear-gradient(135deg,#2EA0FF,#7A4CFF)}
.editTitleBtn:active{transform:scale(.85) rotate(-8deg)}
.editTitleBtn.pop{animation:editPop .5s cubic-bezier(.34,1.56,.64,1)}
@keyframes editPop{0%{transform:scale(.6) rotate(-12deg)}50%{transform:scale(1.3) rotate(8deg)}100%{transform:scale(1) rotate(0)}}
.main{flex:1;display:flex;flex-direction:column;min-width:0}
header{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;padding:18px 28px 0}
.logo{font-size:24px;font-weight:800;letter-spacing:9px;animation:logoGlow 3s ease-in-out infinite}
@keyframes logoGlow{0%,100%{text-shadow:0 0 0 transparent}50%{text-shadow:0 0 22px #0A84FF,0 0 40px #BF5AF266}}
.ver{font-size:10px;color:#ffffff88}
.clearBtn{background:linear-gradient(135deg,rgba(255,255,255,.28),rgba(255,255,255,.08));backdrop-filter:blur(20px) saturate(180%);border:1px solid rgba(255,255,255,.45);box-shadow:0 8px 32px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.7);color:white;padding:10px 16px;border-radius:999px;font-size:10px;font-weight:700;cursor:pointer;transition:transform .22s cubic-bezier(.34,1.56,.64,1);position:relative;overflow:hidden}
.clearBtn::before{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 30%,rgba(255,255,255,.5) 50%,transparent 70%);transform:translateX(-100%);animation:glassShine 3s ease-in-out infinite}
@keyframes glassShine{0%,70%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.clearBtn:hover{transform:scale(1.08) rotate(-2deg)}
.clearBtn:active{transform:scale(.92)}
.orbWrap{position:relative;z-index:2;display:flex;flex-direction:column;align-items:center;gap:8px;padding:10px 0 6px;perspective:900px}
.orbHolder{position:relative;transition:transform .22s cubic-bezier(.2,.8,.2,1);transform-style:preserve-3d;cursor:pointer}
.orbHolder.tremble{animation:orbTremble .6s cubic-bezier(.36,.07,.19,.97) both}
@keyframes orbTremble{0%,100%{transform:translate(0,0) rotate(0)}15%{transform:translate(-6px,3px) rotate(-4deg)}30%{transform:translate(6px,-3px) rotate(4deg)}45%{transform:translate(-5px,-2px) rotate(-3deg)}60%{transform:translate(5px,2px) rotate(3deg)}75%{transform:translate(-3px,1px) rotate(-1deg)}90%{transform:translate(2px,-1px) rotate(1deg)}}
.orb{width:110px;height:110px;position:relative;background:radial-gradient(circle at 32% 26%, #fff, #D8FBFF 12%, #5ED6FF 32%, #0A84FF 58%, #3A2AB8 82%, #08041A);border:1px solid rgba(255,255,255,.85);box-shadow:0 0 50px #0A84FF88,0 0 100px #BF5AF244,inset 0 0 22px #ffffff55, inset -10px -12px 30px rgba(0,0,0,.35);animation:orbFloat 4s ease-in-out infinite, liquidWobble 5s ease-in-out infinite, hue 8s linear infinite}
@keyframes orbFloat{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-7px) scale(1.05)}}
@keyframes liquidWobble{0%,100%{border-radius:50%}20%{border-radius:52% 48% 48% 52% / 52% 48% 48% 52%}40%{border-radius:48% 52% 52% 48% / 48% 52% 52% 48%}60%{border-radius:55% 45% 50% 50% / 45% 55% 50% 50%}80%{border-radius:48% 52% 45% 55% / 55% 45% 52% 48%}}
@keyframes hue{0%{filter:hue-rotate(0deg)}100%{filter:hue-rotate(360deg)}}
.orb::after{content:"";position:absolute;top:18px;left:24px;width:32px;height:12px;background:rgba(255,255,255,.95);border-radius:999px;animation:shineMove 2.6s ease-in-out infinite}
.orb::before{content:"";position:absolute;bottom:12px;right:16px;width:20px;height:9px;background:rgba(255,255,255,.35);border-radius:999px;animation:shineMove2 3s ease-in-out infinite}
@keyframes shineMove{0%,100%{transform:translate(0,0)}50%{transform:translate(16px,7px) scale(.8)}}
@keyframes shineMove2{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-9px,-5px) scale(1.2)}}
.orb.explode{animation:orbExplode .7s cubic-bezier(.34,1.56,.64,1)}
@keyframes orbExplode{0%{transform:scale(1)}30%{transform:scale(.72) rotate(-12deg)}55%{transform:scale(1.38) rotate(7deg)}75%{transform:scale(.9) rotate(-3deg)}100%{transform:scale(1)}}
.halo{position:absolute;width:185px;height:185px;border-radius:50%;background:rgba(10,132,255,.18);top:50%;left:50%;transform:translate(-50%,-50%);animation:haloPulse 3s ease-in-out infinite;pointer-events:none}
.halo2{position:absolute;width:150px;height:150px;border-radius:50%;border:1px solid rgba(255,255,255,.2);top:50%;left:50%;transform:translate(-50%,-50%);animation:spin 12s linear infinite;pointer-events:none}
.halo3{position:absolute;width:130px;height:130px;border-radius:50%;border:1px dashed rgba(255,255,255,.18);top:50%;left:50%;transform:translate(-50%,-50%);animation:spinRev 18s linear infinite;pointer-events:none}
@keyframes haloPulse{0%,100%{transform:translate(-50%,-50%) scale(.9);opacity:.6}50%{transform:translate(-50%,-50%) scale(1.15);opacity:.9}}
@keyframes spin{from{transform:translate(-50%,-50%) rotate(0deg)}to{transform:translate(-50%,-50%) rotate(360deg)}}
@keyframes spinRev{from{transform:translate(-50%,-50%) rotate(360deg)}to{transform:translate(-50%,-50%) rotate(0deg)}}
.status{font-size:11px;letter-spacing:3.5px;color:#8BE9FF;font-weight:700}
.status.thinking{color:#FFD60A;animation:blink .8s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
.divider{position:relative;z-index:2;height:1px;margin:10px 28px 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.25),transparent);animation:dividerFlow 3s linear infinite;background-size:200% 100%}
@keyframes dividerFlow{0%{background-position:0% 0}100%{background-position:200% 0}}
#chat{position:relative;z-index:2;flex:1;overflow-y:auto;padding:16px 28px;display:flex;flex-direction:column;gap:14px;scrollbar-width:thin;scroll-behavior:smooth}
#chat::-webkit-scrollbar{width:6px}#chat::-webkit-scrollbar-thumb{background:rgba(255,255,255,.3);border-radius:999px}
.row{display:flex;width:100%}
.row.user{justify-content:flex-end}.row.bot{justify-content:flex-start}
.bubble{max-width:68%;padding:15px 18px 22px 18px;border-radius:24px;position:relative;box-shadow:0 12px 32px rgba(0,0,0,.35);word-wrap:break-word;white-space:pre-wrap;line-height:1.5;font-size:15px;overflow:hidden}
.bubble.anim-in{animation:popClean .55s cubic-bezier(.34,1.56,.64,1) both}
.bubble:hover{transform:scale(1.02) translateY(-1px);transition:transform .22s cubic-bezier(.34,1.56,.64,1)}
.bubble::before{content:"";position:absolute;top:0;left:0;width:100%;height:100%;background:linear-gradient(110deg,transparent 30%,rgba(255,255,255,.28) 50%,transparent 70%);transform:translateX(-100%);animation:shimmer 3.5s ease-in-out infinite;pointer-events:none;will-change:transform}
.bubble.typing-shimmer::before{animation:none;opacity:0}
.bubble::after{content:"";position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.7),transparent)}
@keyframes shimmer{0%,60%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.row.user .bubble{background:linear-gradient(135deg,rgba(46,160,255,.92),rgba(122,76,255,.92));backdrop-filter:blur(18px) saturate(160%);border:1px solid rgba(255,255,255,.5);box-shadow:0 12px 32px rgba(10,132,255,.25), inset 0 1px 0 rgba(255,255,255,.6)}
.row.bot .bubble{background:linear-gradient(135deg,rgba(42,53,79,.85),rgba(26,34,54,.85));backdrop-filter:blur(20px) saturate(160%);border:1px solid rgba(255,255,255,.28);box-shadow:0 12px 32px rgba(0,0,0,.3), inset 0 1px 0 rgba(255,255,255,.45)}
.bubble b{font-size:9px;letter-spacing:2px;opacity:.7;display:block;margin-bottom:5px;padding-right:42px}
.msg-time{position:absolute;bottom:6px;right:12px;font-size:10px;color:rgba(255,255,255,.55);letter-spacing:.5px;pointer-events:none;display:flex;gap:0}
.row.user .msg-time{color:rgba(255,255,255,.75)}
.msg-time .digit{display:inline-block;animation:digitIn .55s cubic-bezier(.34,1.56,.64,1) both;will-change:transform,opacity}
.msg-time .digit.colon{animation-name:colonIn}
.msg-time.no-anim .digit{animation:none}
@keyframes digitIn{0%{transform:translateY(-14px) scale(.7);opacity:0;filter:blur(2px)}55%{transform:translateY(2px) scale(1.12);opacity:1;filter:blur(0)}100%{transform:translateY(0) scale(1);opacity:1;filter:blur(0)}}
@keyframes colonIn{0%{transform:scale(.4);opacity:0}60%{transform:scale(1.25);opacity:1}100%{transform:scale(1);opacity:1}}
.bubble img.genImg{width:100%;height:auto;display:block;border-radius:16px;margin-top:10px;box-shadow:0 8px 24px rgba(0,0,0,.4);cursor:zoom-in;transition:transform .22s;object-fit:contain;max-height:none}
.bubble img.genImg:hover{transform:scale(1.01)}
.copyBtn{position:absolute;top:8px;right:8px;background:rgba(255,255,255,.15);backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,.35);color:white;font-size:11px;font-weight:700;padding:5px 9px;border-radius:999px;cursor:pointer;z-index:5;transition:transform .18s, background .18s;box-shadow:0 4px 12px rgba(0,0,0,.25)}
.copyBtn:hover{transform:scale(1.1);background:rgba(255,255,255,.3)}
.copyBtn:active{transform:scale(.9)}
.copyBtn.copied{background:rgba(52,199,89,.85);border-color:rgba(255,255,255,.6)}
.limitBox{width:100%;aspect-ratio:1/1;max-width:420px;border-radius:16px;margin-top:10px;background:linear-gradient(135deg,#1a1a2e,#16213e);border:2px dashed rgba(255,255,255,.4);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-align:center;padding:20px}
.limitBox .big{font-size:18px;font-weight:800;letter-spacing:1px}
.limitBox .small{font-size:12px;color:rgba(255,255,255,.7)}
@keyframes popClean{0%{transform:scale(.6) translateY(18px);opacity:0}60%{transform:scale(1.04) translateY(-2px);opacity:1}100%{transform:scale(1) translateY(0);opacity:1}}
.typing{display:flex;gap:6px;align-items:center;background:linear-gradient(135deg,rgba(255,255,255,.28),rgba(255,255,255,.08));backdrop-filter:blur(20px) saturate(180%);border:1px solid rgba(255,255,255,.45);box-shadow:0 8px 32px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.6);padding:14px 18px;border-radius:22px;width:fit-content;animation:popClean .4s cubic-bezier(.34,1.56,.64,1) both}
.dot{width:9px;height:9px;background:#7EDBFF;border-radius:50%;animation:dotBounce .55s ease-in-out infinite}
.dot:nth-child(2){animation-delay:.12s}.dot:nth-child(3){animation-delay:.24s}
@keyframes dotBounce{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-8px) scale(1.3)}}
.inputWrap{position:relative;z-index:2;padding:12px 28px 10px}
.fileTag{display:none;background:linear-gradient(135deg,rgba(10,132,255,.35),rgba(122,76,255,.3));backdrop-filter:blur(18px);border:1px solid rgba(255,255,255,.4);padding:7px 12px;border-radius:999px;font-size:12px;margin-bottom:8px;width:fit-content;animation:popClean .35s cubic-bezier(.34,1.56,.64,1) both;box-shadow:0 6px 20px rgba(10,132,255,.25)}
.fileTag.error{background:linear-gradient(135deg,rgba(255,55,95,.4),rgba(255,120,0,.3));border-color:rgba(255,255,255,.5)}
.pill{background:linear-gradient(135deg,rgba(255,255,255,.28),rgba(255,255,255,.08) 40%,rgba(255,255,255,.18));backdrop-filter:blur(28px) saturate(180%);border:1px solid rgba(255,255,255,.45);box-shadow:0 16px 40px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.75);border-radius:32px;padding:10px 12px;display:flex;gap:12px;align-items:flex-end;transition:box-shadow .3s;position:relative;overflow:hidden}
.pill::before{content:"";position:absolute;top:0;left:10%;right:10%;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.9),transparent)}
.pill::after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 30%,rgba(255,255,255,.28) 50%,transparent 70%);transform:translateX(-100%);animation:glassShine 4s ease-in-out infinite;pointer-events:none}
.pill.focus{border-color:rgba(255,255,255,.7);box-shadow:0 0 0 2px #0A84FF,0 0 0 4px #BF5AF266,0 16px 40px rgba(10,132,255,.35);animation:pillFocusPop .45s cubic-bezier(.34,1.56,.64,1)}
@keyframes pillFocusPop{0%{transform:scale(1)}35%{transform:scale(1.03) translateY(-2px)}60%{transform:scale(.99)}100%{transform:scale(1)}}
.pill.growing{animation:pillGrow .45s cubic-bezier(.34,1.56,.64,1);border-color:rgba(255,255,255,.9) !important;box-shadow:0 0 0 2px #0A84FF,0 0 30px #BF5AF288,0 16px 40px rgba(10,132,255,.45) !important}
@keyframes pillGrow{0%{transform:scale(1)}35%{transform:scale(1.02) translateY(-2px)}60%{transform:scale(.99)}100%{transform:scale(1)}}
.pill textarea{flex:1;background:transparent;border:none;outline:none;color:white;font-size:16px;padding:10px;position:relative;z-index:1;resize:none;overflow-y:hidden;min-height:44px;max-height:200px;line-height:1.4;font-family:inherit;transition:height .35s cubic-bezier(.34,1.56,.64,1), box-shadow .3s}
.pill textarea::placeholder{color:rgba(255,255,255,.6)}
.pill input{flex:1;background:transparent;border:none;outline:none;color:white;font-size:16px;padding:10px;position:relative;z-index:1}
.pill input::placeholder{color:rgba(255,255,255,.6)}
.btnWrap{display:flex;align-items:center;justify-content:center;transition:transform .18s cubic-bezier(.34,1.56,.64,1);will-change:transform}
.btnWrap.trembleSend{animation:btnTremble .5s cubic-bezier(.36,.07,.19,.97) both}
@keyframes btnTremble{0%,100%{transform:translate(0,0) rotate(0)}15%{transform:translate(-4px,2px) rotate(-5deg)}30%{transform:translate(4px,-2px) rotate(5deg)}45%{transform:translate(-3px,-1px) rotate(-4deg)}60%{transform:translate(3px,1px) rotate(4deg)}75%{transform:translate(-2px,1px) rotate(-2deg)}90%{transform:translate(1px,-1px) rotate(1deg)}}
.btn{width:62px;height:62px;min-width:62px;border-radius:32px;border:none;cursor:pointer;color:white;font-size:22px;font-weight:800;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden;transition:transform .22s cubic-bezier(.34,1.56,.64,1), box-shadow .22s, filter .22s}
.btn::before{content:"";position:absolute;top:3px;left:8px;right:8px;height:14px;background:linear-gradient(180deg,rgba(255,255,255,.85),transparent);border-radius:999px;opacity:.7;pointer-events:none}
.btn::after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 30%,rgba(255,255,255,.4) 50%,transparent 70%);transform:translateX(-120%);transition:transform .55s;pointer-events:none}
.btn:hover::after{transform:translateX(120%)}
.btn.blue{background:linear-gradient(135deg,#2EA0FF,#0A84FF 50%,#7A4CFF);background-size:200% 200%;animation:gradMove 4s ease-in-out infinite;border:1px solid rgba(255,255,255,.55);box-shadow:0 12px 32px #0A84FF66, inset 0 1px 0 rgba(255,255,255,.7)}
.btn.glass{background:linear-gradient(135deg,rgba(255,255,255,.38),rgba(255,255,255,.1));backdrop-filter:blur(20px) saturate(180%);border:1px solid rgba(255,255,255,.55);font-size:28px;font-weight:400;box-shadow:0 10px 28px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.75)}
@keyframes gradMove{0%,100%{background-position:0% 0}50%{background-position:100% 100%}}
.btnWrap:hover .btn{transform:scale(1.12) rotate(3deg);box-shadow:0 16px 40px #0A84FF88,0 0 30px #BF5AF255;filter:brightness(1.1)}
.btnWrap:active .btn{transform:scale(.82) rotate(-4deg);transition:transform .07s}
.btn.boing{animation:boingClean .6s cubic-bezier(.34,1.56,.64,1)}
@keyframes boingClean{0%{transform:scale(.82) rotate(-6deg)}35%{transform:scale(1.18) rotate(3deg)}60%{transform:scale(.95) rotate(-1deg)}100%{transform:scale(1) rotate(0)}}
.btn.sendShake{animation:sendShake .55s cubic-bezier(.36,.07,.19,.97) both}
@keyframes sendShake{0%,100%{transform:scale(1) rotate(0)}20%{transform:scale(1.15) rotate(-6deg) translateX(-3px)}40%{transform:scale(1.1) rotate(6deg) translateX(3px)}60%{transform:scale(1.18) rotate(-3deg) translateX(-2px)}80%{transform:scale(1.05) rotate(2deg)}}
#scrollDown{position:fixed;right:28px;bottom:148px;z-index:20;width:56px;height:56px;border-radius:50%;border:1px solid rgba(255,255,255,.6);background:linear-gradient(135deg,rgba(255,255,255,.38),rgba(10,132,255,.45));backdrop-filter:blur(22px) saturate(180%);box-shadow:0 12px 32px rgba(0,0,0,.3),0 0 24px rgba(10,132,255,.35), inset 0 1px 0 rgba(255,255,255,.8);color:white;font-size:22px;cursor:pointer;display:none;align-items:center;justify-content:center;transition:transform .22s cubic-bezier(.34,1.56,.64,1);animation:downBounce 1.6s ease-in-out infinite;overflow:hidden}
#scrollDown::before{content:"";position:absolute;top:3px;left:8px;right:8px;height:12px;background:linear-gradient(180deg,rgba(255,255,255,.9),transparent);border-radius:999px}
#scrollDown.show{display:flex;animation:downIn .45s cubic-bezier(.34,1.56,.64,1) both, downBounce 1.6s .45s ease-in-out infinite}
@keyframes downIn{0%{transform:scale(0) translateY(20px);opacity:0}100%{transform:scale(1) translateY(0);opacity:1}}
@keyframes downBounce{0%,100%{transform:translateY(0)}50%{transform:translateY(6px)}}
#scrollDown:hover{transform:scale(1.15) translateY(-2px)!important;box-shadow:0 16px 40px rgba(10,132,255,.5),0 0 30px #BF5AF255;animation:none}
#scrollDown:active{transform:scale(.85)!important}
#scrollDown .badge{position:absolute;top:-4px;right:-4px;background:#FF375F;color:white;font-size:10px;font-weight:800;min-width:20px;height:20px;border-radius:999px;display:flex;align-items:center;justify-content:center;padding:0 5px;border:2px solid #000}
footer{position:relative;z-index:2;text-align:center;padding:0 0 12px;font-size:9px;letter-spacing:2.6px;color:rgba(255,255,255,.35)}
#imgOverlay{position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.92);backdrop-filter:blur(10px);display:none;align-items:center;justify-content:center;flex-direction:column;gap:16px;padding:20px;animation:overlayIn .35s cubic-bezier(.34,1.56,.64,1) both}
#imgOverlay.show{display:flex}
@keyframes overlayIn{0%{opacity:0;transform:scale(.9)}100%{opacity:1;transform:scale(1)}}
#imgOverlay img{max-width:92vw;max-height:82vh;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,.6);object-fit:contain}
#imgOverlay .closeBtn{position:absolute;top:18px;right:18px;width:52px;height:52px;border-radius:50%;border:1px solid rgba(255,255,255,.6);background:rgba(255,255,255,.15);backdrop-filter:blur(10px);color:white;font-size:22px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:transform .2s}
#imgOverlay .closeBtn:hover{transform:scale(1.15) rotate(90deg);background:rgba(255,55,95,.7)}
#imgOverlay .caption{font-size:13px;color:rgba(255,255,255,.7)}
@media(max-width:800px){.sidebar{display:none}.bubble{max-width:88%}header{padding:14px 16px 0}#chat{padding:12px 16px}.inputWrap{padding:10px 16px 8px}#scrollDown{right:16px;bottom:150px}}
</style></head><body>
<div class="bg" id="bg"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div><div id="stars"></div></div>
<header><div><div class="logo">J A R V I S</div><div class="ver">9.4.5 • IMAGE FIX VRAI • SANS CROP • 120b</div></div><button class="clearBtn" onclick="clearAllMemory()">⌫  MÉMOIRE (TOUT SUPPRIMER)</button></header>
<div class="app">
  <div class="sidebar">
    <button class="newChatBtn" onclick="createNewChat()">➕  Nouveau Chat</button>
    <h3>💬 TES CHATS • MEMOIRE GLOBALE</h3>
    <div id="chatList" style="display:flex;flex-direction:column;gap:8px"></div>
    <div style="margin-top:auto;padding:10px 8px;font-size:10px;color:rgba(255,255,255,.45);line-height:1.5">ℹ️ Chaque nouveau chat se souvient des autres chats.<br>Image : 1 toutes les 45s<br>Le bouton MÉMOIRE en haut supprime TOUT.</div>
  </div>
  <div class="main">
    <div class="orbWrap"><div class="orbHolder" id="orbHolder" onclick="explodeOrb()"><div class="halo"></div><div class="halo2"></div><div class="halo3"></div><div class="orb" id="orb"></div></div><div class="status" id="status">●  SYSTEM ONLINE</div></div>
    <div class="divider"></div>
    <div id="chat"></div>
    <div class="inputWrap"><div class="fileTag" id="fileTag"></div><div class="pill" id="pill"><div class="btnWrap magnetic"><button class="btn glass" onclick="boing(this); document.getElementById('file').click()">+</button></div><textarea id="entry" rows="1" placeholder="Écris quelque chose à JARVIS... ou génère une image..."></textarea><div class="btnWrap magnetic" id="sendWrap"><button class="btn blue" id="sendBtn" onclick="trembleSend(this); send(); spawnConfetti(this)">➤</button></div><input type="file" id="file" hidden onchange="onFile(this)" accept="image/*,.txt,.md,.pdf,.json,.csv,.docx,.py,.js,.html,.css"></div></div>
    <footer>J A R V I S  9.4.5  •  IMAGE FIX VRAI  •  SANS CROP  •  LIQUID GLASS  •  GROQ AI</footer>
  </div>
</div>
<button id="scrollDown" onclick="scrollBottom(true); hideScrollBtn()" title="Retour en bas">↓<span class="badge" id="newMsgBadge" style="display:none">!</span></button>
<div id="imgOverlay"><button class="closeBtn" onclick="closeFullscreen()">✕</button><img id="fullImg" src=""><div class="caption" id="fullCaption">Clique sur ✕ ou sur le fond pour fermer</div></div>
<script>
const chat=document.getElementById('chat');const entry=document.getElementById('entry');const pill=document.getElementById('pill');const statusEl=document.getElementById('status');const orb=document.getElementById('orb');const orbHolder=document.getElementById('orbHolder');const bg=document.getElementById('bg');const scrollBtn=document.getElementById('scrollDown');const badge=document.getElementById('newMsgBadge');const sendWrap=document.getElementById('sendWrap');const chatList=document.getElementById('chatList');
let currentChatId=null, isAtBottom=true, lastTrail=0;
const starsEl=document.getElementById('stars');for(let i=0;i<42;i++){let s=document.createElement('div');s.className='star';s.textContent='•';s.style.left=Math.random()*100+'%';s.style.top=Math.random()*100+'%';s.style.animationDelay=(Math.random()*2)+'s';starsEl.appendChild(s);}
let lastX=0, lastY=0, firstMove=true;
document.addEventListener('mousemove',e=>{
  let x=(e.clientX/window.innerWidth-.5), y=(e.clientY/window.innerHeight-.5);
  bg.style.transform=`translate(${x*-18}px,${y*-14}px)`;
  orbHolder.style.transform=`translate(${x*18}px,${y*12}px) rotateY(${x*18}deg) rotateX(${-y*14}deg)`;
  let now=Date.now();
  if(now-lastTrail>12){
    lastTrail=now;
    let steps = 3;
    if(!firstMove){
      let dx = (e.clientX - lastX) / steps;
      let dy = (e.clientY - lastY) / steps;
      for(let i=0;i<steps;i++){ spawnTrail(e.clientX - dx*i + (Math.random()*8-4), e.clientY - dy*i + (Math.random()*8-4)); }
    }
    spawnTrail(e.clientX, e.clientY);
    lastX = e.clientX; lastY = e.clientY; firstMove = false;
  }
});
function spawnTrail(px, py){
  let t=document.createElement('div'); t.className='trail';
  let colors=['#0A84FF','#BF5AF2','#00D2FF','#FFD60A'];
  let s = 5 + Math.random()*7;
  t.style.width=s+'px'; t.style.height=s+'px';
  t.style.left=(px-s/2)+'px'; t.style.top=(py-s/2)+'px';
  t.style.background=colors[Math.floor(Math.random()*colors.length)];
  t.style.boxShadow='0 0 8px '+t.style.background;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(),650);
  let all = document.querySelectorAll('.trail');
  if(all.length>90){ all[0].remove(); }
}
document.addEventListener('click',e=>{let r=document.createElement('div');r.className='ripple';r.style.left=e.clientX+'px';r.style.top=e.clientY+'px';document.body.appendChild(r);setTimeout(()=>r.remove(),800);});
function explodeOrb(){orb.classList.remove('explode'); void orb.offsetWidth; orb.classList.add('explode');orbHolder.classList.remove('tremble'); void orbHolder.offsetWidth; orbHolder.classList.add('tremble');document.body.classList.remove('shake','jump'); void document.body.offsetWidth; document.body.classList.add('shake');bg.classList.remove('shakeBg'); void bg.offsetWidth; bg.classList.add('shakeBg');spawnConfetti(orb);statusEl.textContent='●  ORBE TOUCHÉE !'; setTimeout(()=>{statusEl.textContent='●  SYSTEM ONLINE';},1200);setTimeout(()=>{document.body.classList.remove('shake'); document.body.classList.add('jump');},550);setTimeout(()=>{document.body.classList.remove('jump'); orbHolder.classList.remove('tremble');},1100);}
function trembleSend(btn){btn.classList.remove('sendShake','boing'); void btn.offsetWidth; btn.classList.add('sendShake');sendWrap.classList.remove('trembleSend'); void sendWrap.offsetWidth; sendWrap.classList.add('trembleSend');document.body.classList.remove('shake'); void document.body.offsetWidth; document.body.classList.add('shake');setTimeout(()=>{document.body.classList.remove('shake'); sendWrap.classList.remove('trembleSend');},600);setTimeout(()=>{btn.classList.remove('sendShake');},650);}
document.querySelectorAll('.magnetic').forEach(wrap=>{wrap.addEventListener('mousemove',e=>{let r=wrap.getBoundingClientRect();let dx=e.clientX-(r.left+r.width/2), dy=e.clientY-(r.top+r.height/2);if(wrap.classList.contains('trembleSend')) return; wrap.style.transform=`translate(${dx*0.28}px,${dy*0.28}px)`;});wrap.addEventListener('mouseleave',()=>{wrap.style.transform='';});});
function boing(el){el.classList.remove('boing');void el.offsetWidth;el.classList.add('boing');}
function spawnConfetti(fromEl){let r=fromEl.getBoundingClientRect();let cx=r.left+r.width/2, cy=r.top+r.height/2;let colors=['#0A84FF','#BF5AF2','#00D2FF','#FFD60A','#FF375F','#34C759'];for(let i=0;i<42;i++){let p=document.createElement('div');p.className='particle';p.style.left=cx+'px';p.style.top=cy+'px';p.style.background=colors[i%colors.length];let a=Math.random()*Math.PI*2, d=70+Math.random()*150;p.style.setProperty('--dx',Math.cos(a)*d+'px');p.style.setProperty('--dy',Math.sin(a)*d-50+'px');p.style.width=(5+Math.random()*8)+'px';p.style.height=p.style.width;document.body.appendChild(p);setTimeout(()=>p.remove(),1100);} }
async function copyBubbleText(btn, fullText){
  let clean = fullText.replace(/\[IMAGE\]https?:\/\/\S+/g, '').replace(/\[LIMIT\]\d+/g, '').trim();
  if(!clean) clean = fullText;
  try{ await navigator.clipboard.writeText(clean); }
  catch(e){ let ta=document.createElement('textarea'); ta.value=clean; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); }
  let old = btn.textContent;
  btn.textContent = '✅ Copié !'; btn.classList.add('copied');
  setTimeout(()=>{ btn.textContent = old; btn.classList.remove('copied'); }, 1200);
}
function scrollBottom(smooth){chat.scrollTo({top:chat.scrollHeight,behavior:smooth?'smooth':'auto'}); hideScrollBtn();}
function hideScrollBtn(){scrollBtn.classList.remove('show'); badge.style.display='none'; isAtBottom=true;}
function showScrollBtn(hasNew){scrollBtn.classList.add('show'); if(hasNew) badge.style.display='flex';}
chat.addEventListener('scroll',()=>{let dist=chat.scrollHeight-chat.scrollTop-chat.clientHeight; isAtBottom=dist<80; if(dist>140) showScrollBtn(false); else hideScrollBtn();});
entry.addEventListener('focus',()=>{ pill.classList.remove('focus'); void pill.offsetWidth; pill.classList.add('focus'); });
entry.addEventListener('blur',()=>pill.classList.remove('focus'));
let lastHeight = 44;
let growTimeout = null;
function autoGrow(){
  entry.style.height='auto';
  let nh = Math.min(200, Math.max(44, entry.scrollHeight));
  entry.style.height = nh + 'px';
  entry.style.overflowY = entry.scrollHeight > 200 ? 'auto' : 'hidden';
  if(nh !== lastHeight){
    lastHeight = nh;
    pill.classList.remove('growing');
    void pill.offsetWidth;
    pill.classList.add('growing');
    clearTimeout(growTimeout);
    growTimeout = setTimeout(()=> pill.classList.remove('growing'), 450);
  }
}
entry.addEventListener('input', autoGrow);
entry.addEventListener('keydown',e=>{
  if(e.key==='Enter' && !e.shiftKey){
    e.preventDefault();
    let b=document.getElementById('sendBtn'); trembleSend(b); send(); spawnConfetti(b);
  }
});
function resetEntry(){
  entry.value='';
  entry.style.height='44px';
  entry.style.overflowY='hidden';
  lastHeight=44;
  pill.classList.remove('growing');
  void pill.offsetWidth;
  pill.classList.add('growing');
  setTimeout(()=> pill.classList.remove('growing'), 450);
}
let attached=null,attachedName="";let fileTagEl=document.getElementById('fileTag');
function onFile(inp){let f=inp.files[0]; if(!f) return;if(f.size>8*1024*1024){ fileTagEl.style.display='block'; fileTagEl.classList.add('error'); fileTagEl.textContent='⚠️ Fichier trop gros (>8 Mo) : '+f.name; attached=null; attachedName=''; inp.value=''; setTimeout(()=>{fileTagEl.style.display='none'; fileTagEl.classList.remove('error')},4000); return;}attachedName=f.name; fileTagEl.classList.remove('error'); fileTagEl.style.display='block'; fileTagEl.textContent='📎 '+f.name+' ('+(f.size/1024).toFixed(0)+' Ko)';let r=new FileReader(); r.onload=()=>{attached=r.result;}; r.onerror=()=>{fileTagEl.textContent='⚠️ Impossible de lire ce fichier'; attached=null;}; r.readAsDataURL(f);}
function openFullscreen(src, caption){
  let o=document.getElementById('imgOverlay');
  document.getElementById('fullImg').src=src;
  document.getElementById('fullCaption').textContent=caption||'Clique sur ✕ pour fermer';
  o.classList.add('show');
}
function closeFullscreen(){
  document.getElementById('imgOverlay').classList.remove('show');
  document.getElementById('fullImg').src='';
}
document.getElementById('imgOverlay').addEventListener('click',e=>{ if(e.target.id==='imgOverlay' || e.target.id==='fullImg') closeFullscreen(); });
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeFullscreen(); });
function makeTitleHtml(title, animate){
  let esc = title.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  if(!animate) return '<span class="titleText">'+esc+'</span>';
  let html = '<span class="titleText">';
  esc.split('').forEach((ch, idx)=>{
    let delay = (idx * 0.05).toFixed(2)+'s';
    let c = ch === ' ' ? '&nbsp;' : ch;
    html += '<span class="chatTitleLetter" style="animation-delay:'+delay+'">'+c+'</span>';
  });
  html += '</span>';
  return html;
}
let knownTitles = {};
async function loadChats(animateNewTitleId=null){
  let r=await fetch('/chats'); let list=await r.json();
  chatList.innerHTML='';
  list.forEach(c=>{
    let d=document.createElement('div'); d.className='chatItem'+(c.id===currentChatId?' active':'');
    let shouldAnimate = (animateNewTitleId === c.id);
    let titleHtml = makeTitleHtml(c.title, shouldAnimate);
    d.innerHTML=`<div class="t">${titleHtml}</div><div class="s">${c.count} msg • ${escapeHtml(c.last||'Nouveau chat')}</div><button class="editTitleBtn" onclick="event.stopPropagation(); editTitle(${c.id}, this)">✏️</button><button class="del" onclick="event.stopPropagation(); deleteChat(${c.id})">✕</button>`;
    d.onclick=()=>switchChat(c.id); chatList.appendChild(d);
    knownTitles[c.id]=c.title;
  });
}
async function editTitle(chatId, btn){
  btn.classList.remove('pop'); void btn.offsetWidth; btn.classList.add('pop');
  let cur = knownTitles[chatId] || '';
  let nv = prompt('Nouveau titre du chat :', cur);
  if(nv===null) return;
  nv = nv.trim();
  if(!nv) return;
  await fetch('/chats/'+chatId+'/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:nv})});
  knownTitles[chatId]=nv;
  await loadChats(chatId);
}
async function createNewChat(){
  let r=await fetch('/chats/new',{method:'POST'}); let data=await r.json();
  currentChatId=data.id; chat.innerHTML=''; addMsg('Nouveau chat. Je me souviens des autres chats. Que puis-je faire ? 😎',false,false);
  await loadChats(); entry.focus();
}
async function switchChat(id){
  currentChatId=id; chat.innerHTML=''; await loadChats();
  let r=await fetch('/history?chat_id='+id); let h=await r.json();
  if(h.length===0) addMsg('Nouveau chat. Je me souviens des autres chats aussi ✨',false,false);
  else h.forEach(m=>addMsg(m.content,m.role==='user',false));
  setTimeout(()=>scrollBottom(false),200);
}
async function deleteChat(id){
  if(!confirm('Supprimer ce chat ? (les autres chats restent)')) return;
  await fetch('/chats/'+id+'/delete',{method:'POST'});
  delete knownTitles[id];
  if(id===currentChatId){ chat.innerHTML=''; }
  await loadChats();
  if(id===currentChatId){
    let r=await fetch('/chats'); let list=await r.json(); if(list.length>0) switchChat(list[0].id);
  }
}
async function clearAllMemory(){
  if(!confirm('⚠️ Supprimer la mémoire de TOUS les chats ? C\'est irréversible.')) return;
  let r=await fetch('/clear',{method:'POST'}); let data=await r.json();
  currentChatId=data.new_chat_id; chat.innerHTML=''; addMsg('Mémoire de TOUS les chats supprimée.',false,false); knownTitles={}; await loadChats();
}
function renderTextWithImage(text, span){
  let mLimit = text.match(/\[LIMIT\](\d+)/);
  if(mLimit){
    let wait = mLimit[1];
    let txt = text.replace(mLimit[0], '').trim();
    span.textContent = txt;
    let box=document.createElement('div'); box.className='limitBox';
    box.innerHTML=`<div style="font-size:42px">⏳</div><div class="big">LIMITE FREE LIMIT</div><div class="small">WAIT ${wait}s</div><div class="small">1 image toutes les 45 sec.<br>Attends ${wait} secondes et redemande.</div>`;
    span.appendChild(document.createElement('br')); span.appendChild(box);
    return;
  }
  let m = text.match(/\[IMAGE\](https?:\/\/\S+)/);
  if(m){
    let txt = text.replace(m[0], '').trim();
    span.textContent = txt;
    let img = document.createElement('img');
    img.src = m[1]; img.className='genImg'; img.alt='Image générée';
    img.title='Clique pour voir en grand écran';
    img.onclick=(e)=>{ e.stopPropagation(); openFullscreen(m[1], txt); };
    span.appendChild(document.createElement('br')); span.appendChild(img);
    let hint=document.createElement('div'); hint.style.fontSize='11px'; hint.style.color='rgba(255,255,255,.5)'; hint.style.marginTop='6px'; hint.textContent='👆 Clique sur l\'image pour la voir en grand écran - elle est en HD, c\'est la bulle qui la réduit';
    span.appendChild(hint);
  } else {
    span.textContent = text;
  }
}
function makeTimeHtml(animate){
  let now = new Date();
  let heure = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0');
  if(!animate) return '<span class="msg-time no-anim">'+heure+'</span>';
  let html = '<span class="msg-time">';
  let chars = heure.split('');
  chars.forEach((ch, idx)=>{
    let cls = ch === ':' ? 'digit colon' : 'digit';
    let delay = (idx * 0.09).toFixed(2) + 's';
    html += '<span class="'+cls+'" style="animation-delay:'+delay+'">'+ch+'</span>';
  });
  html += '</span>';
  return html;
}
let bubbleCount = 0;
function addMsg(text,isUser,typing=true){
  let row=document.createElement('div');row.className='row '+(isUser?'user':'bot');
  let b=document.createElement('div');b.className='bubble anim-in';
  if(!isUser && typing){ b.classList.add('typing-shimmer'); }
  if(!isUser){ bubbleCount++; }
  let copyHtml = !isUser ? `<button class="copyBtn">📋 Copier</button>` : '';
  let shouldAnimateTime = (isUser || typing);
  b.innerHTML='<b>'+(isUser?'TOI':'JARVIS')+'</b><span></span>'+copyHtml+makeTimeHtml(shouldAnimateTime);
  row.appendChild(b);chat.appendChild(row);
  if(!isAtBottom && !isUser){ showScrollBtn(true); } else { setTimeout(()=>scrollBottom(true),60); }
  let span=b.querySelector('span');
  let copyBtn = b.querySelector('.copyBtn');
  if(copyBtn){ copyBtn.onclick = (e)=>{ e.stopPropagation(); copyBubbleText(copyBtn, text); }; }
  function finishShimmer(){ b.classList.remove('typing-shimmer'); void b.offsetWidth; }
  if(!typing || isUser){
    if(text.includes('[IMAGE]') || text.includes('[LIMIT]')){ renderTextWithImage(text, span); }
    else span.textContent=text;
    return;
  }
  if(text.includes('[IMAGE]') || text.includes('[LIMIT]')){ renderTextWithImage(text, span); if(isAtBottom) scrollBottom(true); finishShimmer(); return; }
  let i=0;
  function typeStep(){
    i += 28;
    span.textContent = text.slice(0, i);
    if(isAtBottom) chat.scrollTop = chat.scrollHeight;
    if(i < text.length){ requestAnimationFrame(typeStep); }
    else { span.textContent = text; finishShimmer(); }
  }
  requestAnimationFrame(typeStep);
}
function escapeHtml(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
let typingEl=null;function showTyping(){typingEl=document.createElement('div');typingEl.className='typing';typingEl.innerHTML='<div class="dot"></div><div class="dot"></div><div class="dot"></div><span style="font-size:9px;font-weight:700;letter-spacing:1.5px;margin-left:4px">JARVIS RÉFLÉCHIT</span>';chat.appendChild(typingEl); if(isAtBottom) scrollBottom(true);}function hideTyping(){if(typingEl) typingEl.remove();typingEl=null;}
async function send(){
  let q=entry.value.trim(); if(!q && !attached) return; if(!q) q="Décris cette image en détail.";
  let disp=q+(attachedName?'\n\n📎 '+attachedName:''); addMsg(disp,true,false); resetEntry();
  let fd=attached,fn=attachedName; attached=null; attachedName=''; fileTagEl.style.display='none'; document.getElementById('file').value='';
  statusEl.textContent='●  PROCESSING'; statusEl.classList.add('thinking'); showTyping();
  try{let res=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:q,file:fd,fileName:fn,chat_id:currentChatId})});let data=await res.json();hideTyping();if(data.error) addMsg('Erreur :\n'+data.error,false,false);else addMsg(data.reply,false,true); if(data.new_title){ await loadChats(data.new_title_id); } else { await loadChats(); }}catch(e){hideTyping();addMsg('Erreur réseau : '+e,false,false);}
  statusEl.textContent='●  SYSTEM ONLINE'; statusEl.classList.remove('thinking'); entry.focus();
}
async function init(){
  let r=await fetch('/chats'); let list=await r.json();
  if(list.length>0) currentChatId=list[0].id;
  await loadChats(); await switchChat(currentChatId);
  entry.focus();
}
init();
</script></body></html>
"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send_json(self, obj):
        data=json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        try:
            if self.path=='/' or self.path=='/index.html':
                data=HTML.encode('utf-8'); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
            elif self.path=='/chats':
                self.send_json(mem.list_chats())
            elif self.path.startswith('/history'):
                from urllib.parse import urlparse, parse_qs
                qs=parse_qs(urlparse(self.path).query); cid=int(qs.get('chat_id',[1])[0])
                self.send_json(mem.load(cid,30))
            else: self.send_response(404); self.end_headers()
        except Exception as e: print("GET error", e); traceback.print_exc()
    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length',0) or 0)
            body=self.rfile.read(length) if length>0 else b'{}'
            try: payload=json.loads(body.decode('utf-8'))
            except: payload={}
            if self.path=='/clear':
                new_id=mem.clear_all(); self.send_json({"ok":True,"new_chat_id":new_id}); return
            if self.path=='/chats/new':
                nid=mem.create_chat(); self.send_json({"id":nid}); return
            if self.path.startswith('/chats/') and self.path.endswith('/rename'):
                try:
                    cid=int(self.path.split('/')[2])
                    new_title=(payload.get('title') or '').strip()[:35]
                    if new_title:
                        mem.set_title(cid, force_french_title(new_title))
                    self.send_json({"ok":True,"title":new_title})
                except Exception as e:
                    self.send_json({"ok":False,"error":str(e)})
                return
            if self.path.startswith('/chats/') and self.path.endswith('/delete'):
                try: cid=int(self.path.split('/')[2]); mem.delete_chat(cid)
                except: pass
                self.send_json({"ok":True}); return
            if self.path=='/chat':
                global LAST_IMAGE_TIME
                if client is None:
                    self.send_json({"error":"CLE MANQUANTE : mets ta vraie clé dans GROQ_API_KEY ou dans API_KEY puis relance. Fais aussi : python -m pip install groq"}); return
                q=payload.get('message','') or 'Décris cette image.'
                file_data=payload.get('file'); file_name=payload.get('fileName','')
                chat_id=int(payload.get('chat_id') or 1)
                disp=q + (f"\n\n📎 {file_name}" if file_name else "")
                mem.save(chat_id, "user", disp)
                new_name, is_not_lenny = detect_name_change(q)
                if new_name:
                    mem.clear_name_facts()
                    mem.save_fact(f"Prénom utilisateur : {new_name}")
                elif is_not_lenny:
                    mem.clear_name_facts()
                    mem.save_fact("L'utilisateur n'est PAS Lenny, demande-lui son prénom et retiens-le")
                for f in extract_facts(q, chat_id):
                    if not f.startswith("Prénom utilisateur") and "PAS Lenny" not in f:
                        mem.save_fact(f)
                current_name = mem.get_user_name()
                new_title = None
                new_title_id = None
                if is_image_request(q) and not file_data:
                    now = time.time()
                    elapsed = now - LAST_IMAGE_TIME
                    if LAST_IMAGE_TIME != 0 and elapsed < IMAGE_COOLDOWN:
                        wait = int(IMAGE_COOLDOWN - elapsed) + 1
                        ans = f"Trop vite ! Attends encore un peu 😅\n[LIMIT]{wait}"
                        mem.save(chat_id, "assistant", ans)
                        self.send_json({"reply": ans}); return
                    LAST_IMAGE_TIME = now
                    prompt_clean = q
                    for w in ["génère une image de", "genere une image de", "crée une image de", "cree une image de", "fais une image de", "génère une image", "genere une image", "génère", "genere", "dessine", "crée une image", "cree une image", "une image de", "image de", "fais une image", "fait une image"]:
                        prompt_clean = prompt_clean.replace(w, "").replace(w.capitalize(), "")
                    prompt_clean = prompt_clean.strip(" :,.!") or "un paysage magnifique"
                    url = make_image_url(prompt_clean)
                    ans = f"Voilà ton image : {prompt_clean} 🔥\n[IMAGE]{url}"
                    mem.save(chat_id, "assistant", ans)
                    cur_title = mem.get_title(chat_id)
                    cnt = mem.c.execute("SELECT COUNT(*) FROM messages WHERE chat_id=?", (chat_id,)).fetchone()[0]
                    if cur_title.startswith("Chat ") and cnt >= 4:
                        hist_for_title = mem.load(chat_id, 6)
                        txt_title = "\n".join([f"{m['role']}: {m['content'][:300]}" for m in hist_for_title])
                        t = generate_chat_title(txt_title)
                        if t:
                            mem.set_title(chat_id, t)
                            new_title = t
                            new_title_id = chat_id
                    self.send_json({"reply": ans, "new_title": new_title, "new_title_id": new_title_id}); return
                is_image = isinstance(file_data,str) and file_data.startswith('data:image')
                if is_image:
                    if len(file_data) > 6_000_000:
                        self.send_json({"error":"Image trop grosse (> ~4 Mo)."}); return
                    last_err=""
                    for model in VISION_MODELS:
                        try:
                            facts = mem.load_facts()
                            global_ctx = mem.load_global(chat_id, 10)
                            global_txt = "\n".join([f"{m['role']}: {m['content'][:300]}" for m in global_ctx])
                            sys_prompt = build_system_prompt(current_name if current_name else "l'utilisateur")
                            sys = sys_prompt + ("\n\n[Infos sur l'utilisateur: "+", ".join(facts)+"]" if facts else "") + ("\n\n[Mémoire autres chats: "+global_txt+"]" if global_txt else "")
                            c=client.chat.completions.create(model=model, messages=[{"role":"system","content":sys},{"role":"user","content":[{"type":"text","text":q+" (Réponds amical, 1-2 emojis max, 2-4 phrases, ne devine pas ce que tu ne vois pas)"},{"type":"image_url","image_url":{"url":file_data}}]}], temperature=0.6, max_completion_tokens=500)
                            ans=c.choices[0].message.content or "Pas de réponse."; mem.save(chat_id, "assistant", ans); self.send_json({"reply":ans}); return
                        except Exception as e: last_err=str(e); print(f"Vision {model} failed:", e); continue
                    self.send_json({"error":f"Groq a refusé : {last_err[:400]}"}); return
                hist=mem.load(chat_id, 40)
                global_hist=mem.load_global(chat_id, 20)
                facts = mem.load_facts()
                msgs=[{"role":"system","content": build_system_prompt(current_name if current_name else "l'utilisateur")}]
                if facts:
                    msgs.append({"role":"system","content":"Infos retenues sur l'utilisateur (utilise-les, ne les réinvente pas) :\n"+"\n".join(facts)})
                if global_hist:
                    msgs.append({"role":"system","content":"Mémoire des AUTRES chats :\n"+"\n".join([f"{m['role']}: {m['content'][:400]}" for m in global_hist])})
                msgs+=hist
                if isinstance(file_data,str) and file_data.startswith('data:'):
                    try:
                        header, b64 = file_data.split(',',1)
                        if 'text/' in header or 'json' in header or 'csv' in header or file_name.lower().endswith(('.txt','.md','.json','.csv','.py','.js','.html','.css')):
                            txt=base64.b64decode(b64).decode('utf-8', errors='ignore')[:30000]
                            msgs[-1]={"role":"user","content":q+f"\n\n--- FICHIER {file_name} ---\n"+txt+" (Réponds amical, 1-2 emojis max)"}
                        elif file_name.lower().endswith('.pdf'):
                            msgs[-1]={"role":"user","content":q+f"\n\n[PDF : {file_name}. Dis de copier-coller le texte.]"}
                        else:
                            msgs[-1]={"role":"user","content":q+f"\n\n[Fichier {file_name} illisible.]"}
                    except: msgs[-1]={"role":"user","content":q+"\n\n[Erreur lecture fichier]"}
                else:
                    msgs[-1]={"role":"user","content":disp}
                try:
                    ans = call_groq(msgs, max_tokens=800, user_name=current_name)
                    mem.save(chat_id, "assistant", ans)
                    cur_title = mem.get_title(chat_id)
                    cnt = mem.c.execute("SELECT COUNT(*) FROM messages WHERE chat_id=?", (chat_id,)).fetchone()[0]
                    if cur_title.startswith("Chat ") and cnt >= 4:
                        hist_for_title = mem.load(chat_id, 6)
                        txt_title = "\n".join([f"{m['role']}: {m['content'][:300]}" for m in hist_for_title])
                        t = generate_chat_title(txt_title)
                        if t:
                            mem.set_title(chat_id, t)
                            new_title = t
                            new_title_id = chat_id
                    self.send_json({"reply":ans, "new_title": new_title, "new_title_id": new_title_id})
                except Exception as e: print("Groq error:", e); traceback.print_exc(); self.send_json({"error":str(e)})
                return
            self.send_response(404); self.end_headers()
        except Exception as e:
            print("POST error", e); traceback.print_exc()
            try: self.send_json({"error":str(e)})
            except: pass

def main():
    print(f"=== JARVIS {VERSION} EN LIGNE ===")
    print(f"Port : {PORT} - Host : 0.0.0.0")
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    # En local, on ouvre le navigateur. Sur Render, on ne l'ouvre pas.
    if not os.environ.get("RENDER"):
        threading.Timer(1.0, lambda: webbrowser.open(f'http://localhost:{PORT}')).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nBye")
if __name__=="__main__": main()
