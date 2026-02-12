# Agents du projet SunnyVibeScheduler

Description courte:

Ce dépôt contient une application web légère pour gérer les utilisateurs et la réservation de la salle d'entraînement du "Sunny Vibe Nutrition".

But:

- Gérer les comptes utilisateur (inscription / connexion).
- Permettre la réservation d'une plage horaire dans le calendrier de la salle d'entraînement.

Stack technique:

- Backend: Python + Flask (serveur léger)
- Frontend: HTML / CSS (templates Jinja2)
- Base de données: SQL (SQLite initialement, possibilité de migrer vers PostgreSQL)

Schéma de base de données (première ébauche):

- Table `users`
  - id INTEGER PRIMARY KEY
  - email TEXT UNIQUE NOT NULL
  - password_hash TEXT NOT NULL
  - full_name TEXT

- Table `bookings`
  - id INTEGER PRIMARY KEY
  - user_id INTEGER REFERENCES users(id)
  - start DATETIME NOT NULL
  - end DATETIME NOT NULL
  - title TEXT
  - created_at DATETIME DEFAULT CURRENT_TIMESTAMP

Fonctionnalités prévues:

- Inscription / Connexion
- Création, lecture, annulation de réservations
- Visualisation calendrier (vue quotidienne / hebdomadaire)
- Vérification de conflits de créneaux

Développement local (instructions rapides):

1. Créer un environnement virtuel: `python -m venv venv`
2. Activer l'environnement (PowerShell): `.\\venv\\Scripts\\Activate.ps1`
3. Installer les dépendances: `pip install -r requirements.txt`
4. Lancer l'app: `python app.py` (écoute sur le port 39048)

Notes:

- Pour commencer simplement, l'application utilise SQLite. Lorsqu'on passera en production, migrer vers une base plus robuste (Postgres) et activer HTTPS.
- Ce fichier `agents.md` servira de point d'entrée pour les instructions et le cadrage produit.
