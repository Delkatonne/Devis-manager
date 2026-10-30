# Générateur de devis (Flask + Postgres)

## Lancer en local
    python -m venv venv && source venv/bin/activate   # Windows : venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env     # remplir SECRET_KEY et DATABASE_URL
    python app.py            # http://127.0.0.1:5000
Sans e-mail configuré, le lien « mot de passe oublié » s'affiche dans la console.

## Déployer sur Vercel (zéro configuration)
1. Créer une base Postgres gratuite : Neon (neon.tech) ou Supabase, et copier la chaîne de connexion (`DATABASE_URL`).
2. Pousser ce dossier sur GitHub.
3. vercel.com/new > importer le dépôt (Flask est détecté automatiquement via `app.py`).
4. Settings > Environment Variables : `SECRET_KEY`, `DATABASE_URL`, `BREVO_API_KEY`, `MAIL_FROM`.
5. Deploy. Les tables sont créées automatiquement à la première requête.

## E-mails (mot de passe oublié)
Brevo (offre gratuite) : créer un compte, valider l'adresse expéditrice (Senders), créer une clé API
(SMTP & API > API Keys). Le destinataire est le Gmail saisi par l'entreprise à l'inscription.

## Notes
- Fichiers statiques dans `public/static/`. Logos stockés en base (limite 2 Mo).
- Vercel est sans état : rien n'est écrit sur disque, tout est dans Postgres.
