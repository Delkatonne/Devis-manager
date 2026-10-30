# Générateur de devis (Flask)

## Lancer en local
    python -m venv venv && source venv/bin/activate   # Windows : venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env     # puis remplir SECRET_KEY, SMTP_USER, SMTP_PASSWORD
    python app.py            # http://127.0.0.1:5000

## Mot de passe oublié (Gmail)
1. Active la validation en 2 étapes sur le compte Gmail expéditeur.
2. Crée un « mot de passe d'application » (compte Google > Sécurité) et mets-le dans SMTP_PASSWORD.
3. L'e-mail de récupération est envoyé au Gmail saisi par l'entreprise à l'inscription (lien valable 1 h, usage unique).
Sans SMTP configuré, le lien s'affiche dans la console du serveur (utile en test).

## Production
    gunicorn app:app
Sauvegarder régulièrement `devis.db` et le dossier `uploads/` (logos).
