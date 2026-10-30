import os, json, uuid, smtplib, urllib.request
from datetime import date
from email.message import EmailMessage
from functools import wraps
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, abort, jsonify, Response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from itsdangerous import URLSafeTimedSerializer, BadSignature

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))
# Les fichiers statiques sont dans public/static (servis par le CDN de Vercel, et par Flask en local)
app = Flask(__name__, static_folder="public/static", static_url_path="/static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(SECRET_KEY=os.getenv("SECRET_KEY", "change-me"), MAX_CONTENT_LENGTH=2 * 1024 * 1024,
                  SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=bool(os.getenv("VERCEL")))
DB_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS companies(id SERIAL PRIMARY KEY, name TEXT NOT NULL, admin TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL, logo BYTEA, logo_type TEXT);
CREATE TABLE IF NOT EXISTS quotes(id SERIAL PRIMARY KEY, cid INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    num TEXT, client TEXT DEFAULT '', objet TEXT DEFAULT '', valid TEXT DEFAULT '30',
    cur TEXT DEFAULT 'FCFA', items TEXT DEFAULT '[]');"""
_ready = False

def db():
    global _ready
    if "db" not in g:
        if not DB_URL: raise RuntimeError("DATABASE_URL manquante")
        g.db = psycopg.connect(DB_URL, row_factory=dict_row)
        if not _ready:
            g.db.execute(SCHEMA); g.db.commit(); _ready = True
    return g.db

@app.teardown_appcontext
def _close(e):
    d = g.pop("db", None)
    if d: d.close()

def me():
    if "cid" not in session: return None
    if "me" not in g:
        g.me = db().execute("SELECT id,name,admin,email,pw,(logo IS NOT NULL) AS has_logo "
                            "FROM companies WHERE id=%s", (session["cid"],)).fetchone()
    return g.me

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
        if key and sender:  # API HTTPS (Brevo) : recommandé en ligne
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=json.dumps({"sender": {"name": "Devis", "email": sender}, "to": [{"email": to}],
                                 "subject": subject, "textContent": body}).encode(),
                headers={"api-key": key, "content-type": "application/json", "accept": "application/json"})
            urllib.request.urlopen(req, timeout=20).read()
        elif u and p:  # SMTP Gmail (surtout en local)
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
        data, ltype = None, None
        fl = request.files.get("logo")
        if fl and fl.filename:
            ltype = TYPES.get(fl.filename.rsplit(".", 1)[-1].lower())
            if not ltype:
                flash("Logo : formats acceptés png, jpg, webp, gif.", "err")
                return render_template("register.html")
            data = fl.read()
        try:
            cid = db().execute("INSERT INTO companies(name,admin,email,pw,logo,logo_type) "
                               "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
                               (name, admin, email, generate_password_hash(pw), data, ltype)).fetchone()["id"]
            db().commit()
        except psycopg.errors.UniqueViolation:
            db().rollback()
            flash("Un compte existe déjà avec cet e-mail.", "err")
            return render_template("register.html")
        session.clear(); session["cid"] = cid
        return redirect(url_for("list_quotes"))
    return render_template("register.html")

@app.route("/connexion", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        c = db().execute("SELECT id,pw FROM companies WHERE email=%s",
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
        c = db().execute("SELECT id,pw FROM companies WHERE email=%s", (email,)).fetchone()
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
    c = db().execute("SELECT id,pw FROM companies WHERE id=%s", (d["id"],)).fetchone()
    if not c or c["pw"][-12:] != d["h"]:
        flash("Lien déjà utilisé ou invalide.", "err"); return redirect(url_for("forgot"))
    if request.method == "POST":
        p = request.form.get("password", "")
        if len(p) < 6 or p != request.form.get("password2"):
            flash("Mots de passe différents ou trop courts (6 caractères min.).", "err")
        else:
            db().execute("UPDATE companies SET pw=%s WHERE id=%s", (generate_password_hash(p), c["id"]))
            db().commit(); flash("Mot de passe modifié. Connectez-vous.", "ok")
            return redirect(url_for("login"))
    return render_template("reset.html")

@app.route("/logo/<int:cid>")
def logo(cid):
    r = db().execute("SELECT logo, logo_type FROM companies WHERE id=%s", (cid,)).fetchone()
    if not r or not r["logo"]: abort(404)
    return Response(bytes(r["logo"]), mimetype=r["logo_type"],
                    headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})

def own(qid):
    q = db().execute("SELECT * FROM quotes WHERE id=%s AND cid=%s", (qid, session["cid"])).fetchone()
    if not q: abort(404)
    return q

@app.route("/devis")
@login_required
def list_quotes():
    rows = db().execute("SELECT * FROM quotes WHERE cid=%s ORDER BY id DESC", (session["cid"],)).fetchall()
    out = [dict(r, total=sum(i["q"] * i["p"] for i in json.loads(r["items"]))) for r in rows]
    return render_template("list.html", quotes=out)

@app.post("/devis/nouveau")
@login_required
def new_quote():
    last = 0
    for r in db().execute("SELECT num FROM quotes WHERE cid=%s", (session["cid"],)).fetchall():
        try: last = max(last, int(r["num"].split("-")[-1]))
        except ValueError: pass
    items = json.dumps([{"t": "m", "d": "", "q": 1, "p": 0}, {"t": "o", "d": "", "q": 1, "p": 0}])
    qid = db().execute("INSERT INTO quotes(cid,num,items) VALUES(%s,%s,%s) RETURNING id",
                       (session["cid"], f"DV-{date.today().year}-{last+1:03d}", items)).fetchone()["id"]
    db().commit()
    return redirect(url_for("edit_quote", qid=qid))

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
    db().execute("UPDATE quotes SET client=%s,objet=%s,valid=%s,cur=%s,items=%s WHERE id=%s",
                 (str(d.get("client", ""))[:120], str(d.get("objet", ""))[:200],
                  str(d.get("valid", ""))[:10], str(d.get("cur", "FCFA"))[:10], json.dumps(items), qid))
    db().commit(); return jsonify(ok=True)

@app.post("/devis/<int:qid>/supprimer")
@login_required
def delete_quote(qid):
    own(qid); db().execute("DELETE FROM quotes WHERE id=%s", (qid,)); db().commit()
    return redirect(url_for("list_quotes"))

if __name__ == "__main__":
    app.run(debug=True)
