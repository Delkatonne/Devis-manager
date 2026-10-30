import os, json, sqlite3, smtplib, uuid, urllib.request
from email.message import EmailMessage
from functools import wraps
from dotenv import load_dotenv
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, abort, jsonify, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from itsdangerous import URLSafeTimedSerializer, BadSignature

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(SECRET_KEY=os.getenv("SECRET_KEY", "change-me"),
                  MAX_CONTENT_LENGTH=3 * 1024 * 1024, SESSION_COOKIE_SAMESITE="Lax")
DATA = os.getenv("DATA_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or BASE  # volume persistant sur Railway
DB = os.path.join(DATA, "devis.db")
LOGOS = os.path.join(DATA, "uploads")
os.makedirs(LOGOS, exist_ok=True)

with sqlite3.connect(DB) as c:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY, name TEXT, admin TEXT,
        email TEXT UNIQUE, pw TEXT, logo TEXT);
    CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY, cid INTEGER, num TEXT,
        client TEXT DEFAULT '', objet TEXT DEFAULT '', valid TEXT DEFAULT '30',
        cur TEXT DEFAULT 'FCFA', items TEXT DEFAULT '[]');""")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def _close(e):
    d = g.pop("db", None)
    if d: d.close()

def me():
    if "cid" not in session: return None
    return db().execute("SELECT * FROM companies WHERE id=?", (session["cid"],)).fetchone()

@app.context_processor
def ctx(): return {"co": me()}

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not me():
            session.clear(); return redirect(url_for("login"))
        return f(*a, **k)
    return w

def ser(): return URLSafeTimedSerializer(app.config["SECRET_KEY"])
def nb(v):
    try: return max(0, float(v))
    except (TypeError, ValueError): return 0

def send_reset(to, link):
    subject = "Réinitialisation de votre mot de passe"
    body = ("Bonjour,\n\nCliquez sur ce lien pour choisir un nouveau mot de passe "
            f"(valable 1 heure, usage unique) :\n{link}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.")
    key, sender = os.getenv("BREVO_API_KEY"), os.getenv("MAIL_FROM")
    u, p = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    try:
        if key and sender:  # API HTTPS : fonctionne sur Railway (le SMTP y est bloqué hors plan Pro)
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=json.dumps({"sender": {"name": "Devis", "email": sender}, "to": [{"email": to}],
                                 "subject": subject, "textContent": body}).encode(),
                headers={"api-key": key, "content-type": "application/json", "accept": "application/json"})
            urllib.request.urlopen(req, timeout=20).read()
        elif u and p:  # SMTP Gmail (en local ou hébergeur qui autorise le SMTP)
            m = EmailMessage(); m["Subject"] = subject; m["From"] = u; m["To"] = to; m.set_content(body)
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as sm:
                sm.login(u, p); sm.send_message(m)
        else:
            print("\n>>> LIEN DE RÉINITIALISATION (e-mail non configuré) :", link, "\n")
    except Exception as e:
        print("Erreur d'envoi e-mail :", e)

@app.route("/")
def home(): return redirect(url_for("list_quotes" if me() else "login"))

@app.route("/inscription", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name, admin = f.get("name", "").strip(), f.get("admin", "").strip()
        email, pw = f.get("email", "").strip().lower(), f.get("password", "")
        if not (name and admin and "@" in email and len(pw) >= 6):
            flash("Remplissez tous les champs (mot de passe : 6 caractères minimum).", "err")
            return render_template("register.html")
        logo = ""
        fl = request.files.get("logo")
        if fl and fl.filename:
            ext = fl.filename.rsplit(".", 1)[-1].lower()
            if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
                flash("Logo : formats acceptés png, jpg, webp, gif.", "err")
                return render_template("register.html")
            logo = uuid.uuid4().hex + "." + ext
            fl.save(os.path.join(LOGOS, logo))
        try:
            cur = db().execute("INSERT INTO companies(name,admin,email,pw,logo) VALUES(?,?,?,?,?)",
                               (name, admin, email, generate_password_hash(pw), logo))
            db().commit()
        except sqlite3.IntegrityError:
            flash("Un compte existe déjà avec cet e-mail.", "err")
            return render_template("register.html")
        session.clear(); session["cid"] = cur.lastrowid
        return redirect(url_for("list_quotes"))
    return render_template("register.html")

@app.route("/connexion", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        c = db().execute("SELECT * FROM companies WHERE email=?",
                         (request.form.get("email", "").strip().lower(),)).fetchone()
        if c and check_password_hash(c["pw"], request.form.get("password", "")):
            session.clear(); session["cid"] = c["id"]
            return redirect(url_for("list_quotes"))
        flash("E-mail ou mot de passe incorrect.", "err")
    return render_template("login.html")

@app.post("/deconnexion")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/mot-de-passe-oublie", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        c = db().execute("SELECT * FROM companies WHERE email=?", (email,)).fetchone()
        if c:
            tok = ser().dumps({"id": c["id"], "h": c["pw"][-12:]}, salt="reset")
            send_reset(email, url_for("reset", token=tok, _external=True))
        flash("Si cet e-mail correspond à un compte, un lien de réinitialisation vient d'être envoyé.", "ok")
        return redirect(url_for("login"))
    return render_template("forgot.html")

@app.route("/reinitialiser/<token>", methods=["GET", "POST"])
def reset(token):
    try: d = ser().loads(token, salt="reset", max_age=3600)
    except BadSignature:
        flash("Lien invalide ou expiré.", "err"); return redirect(url_for("forgot"))
    c = db().execute("SELECT * FROM companies WHERE id=?", (d["id"],)).fetchone()
    if not c or c["pw"][-12:] != d["h"]:
        flash("Lien déjà utilisé ou invalide.", "err"); return redirect(url_for("forgot"))
    if request.method == "POST":
        p = request.form.get("password", "")
        if len(p) < 6 or p != request.form.get("password2"):
            flash("Mots de passe différents ou trop courts (6 caractères min.).", "err")
        else:
            db().execute("UPDATE companies SET pw=? WHERE id=?", (generate_password_hash(p), c["id"]))
            db().commit(); flash("Mot de passe modifié. Connectez-vous.", "ok")
            return redirect(url_for("login"))
    return render_template("reset.html")

@app.route("/logo/<f>")
def logo(f): return send_from_directory(LOGOS, f)

def own(qid):
    q = db().execute("SELECT * FROM quotes WHERE id=? AND cid=?", (qid, session["cid"])).fetchone()
    if not q: abort(404)
    return q

@app.route("/devis")
@login_required
def list_quotes():
    rows = db().execute("SELECT * FROM quotes WHERE cid=? ORDER BY id DESC", (session["cid"],)).fetchall()
    out = [dict(r, total=sum(i["q"] * i["p"] for i in json.loads(r["items"]))) for r in rows]
    return render_template("list.html", quotes=out)

@app.post("/devis/nouveau")
@login_required
def new_quote():
    from datetime import date
    last = 0
    for r in db().execute("SELECT num FROM quotes WHERE cid=?", (session["cid"],)):
        try: last = max(last, int(r["num"].split("-")[-1]))
        except ValueError: pass
    items = json.dumps([{"t": "m", "d": "", "q": 1, "p": 0}, {"t": "o", "d": "", "q": 1, "p": 0}])
    cur = db().execute("INSERT INTO quotes(cid,num,items) VALUES(?,?,?)",
                       (session["cid"], f"DV-{date.today().year}-{last+1:03d}", items))
    db().commit()
    return redirect(url_for("edit_quote", qid=cur.lastrowid))

@app.route("/devis/<int:qid>")
@login_required
def edit_quote(qid):
    q = dict(own(qid)); q["items"] = json.loads(q["items"])
    return render_template("edit.html", q=q)

@app.post("/devis/<int:qid>/save")
@login_required
def save_quote(qid):
    own(qid); d = request.get_json(force=True)
    items = [{"t": "m" if r.get("t") == "m" else "o", "d": str(r.get("d", ""))[:200],
              "q": nb(r.get("q")), "p": nb(r.get("p"))} for r in d.get("items", [])[:200]]
    db().execute("UPDATE quotes SET client=?,objet=?,valid=?,cur=?,items=? WHERE id=?",
                 (str(d.get("client", ""))[:120], str(d.get("objet", ""))[:200],
                  str(d.get("valid", ""))[:10], str(d.get("cur", "FCFA"))[:10], json.dumps(items), qid))
    db().commit(); return jsonify(ok=True)

@app.post("/devis/<int:qid>/supprimer")
@login_required
def delete_quote(qid):
    own(qid); db().execute("DELETE FROM quotes WHERE id=?", (qid,)); db().commit()
    return redirect(url_for("list_quotes"))

if __name__ == "__main__":
    app.run(debug=True)
