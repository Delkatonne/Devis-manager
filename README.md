# Générateur de devis (Flask)

## Lancer en local
    python -m venv venv && source venv/bin/activate   # Windows : venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env     # remplir SECRET_KEY (+ option e-mail)
    python app.py            # http://127.0.0.1:5000
Sans e-mail configuré, le lien « mot de passe oublié » s'affiche dans la console.

## Déployer sur Railway
1. Pousser le projet sur GitHub, puis Railway > New Project > Deploy from GitHub repo.
2. Service > Settings > Volumes : ajouter un Volume monté sur `/data` (garde `devis.db` et les logos).
3. Service > Variables : `SECRET_KEY`, `BREVO_API_KEY`, `MAIL_FROM` (voir ci-dessous).
4. Service > Settings > Networking : Generate Domain.
Le `Procfile` lance `gunicorn`. Railway fournit `PORT` et `RAILWAY_VOLUME_MOUNT_PATH` automatiquement.

## E-mails sur Railway (important)
Railway bloque le SMTP (Gmail inclus) sur les plans Free/Trial/Hobby : il faut une API HTTPS.
Avec Brevo (offre gratuite) : créer un compte, ajouter et valider l'adresse expéditrice (Senders),
créer une clé API (SMTP & API > API Keys), puis renseigner `BREVO_API_KEY` et `MAIL_FROM`.
Le destinataire reste le Gmail saisi par l'entreprise à l'inscription.
