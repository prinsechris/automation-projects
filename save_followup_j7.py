#!/usr/bin/env python3
"""Follow-up J+7 — nouvel angle, question ouverte (Chris Voss style).

A lancer dimanche 9 mars vers 8h.
Sujet different pour se demarquer dans la boite mail.
Question calibree : toute reponse ouvre une conversation.
"""

import imaplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

IMAP_HOST = "imap.zoho.eu"
IMAP_PORT = 993
SMTP_USER = "contact@adaptive-logic.fr"
SMTP_PASS = "PJe4ad!NGjqhY8C5"

PROSPECTS = [
    {
        "nom": "La Maison des Fondues",
        "email": "maisondesfonduesavignon@gmail.com",
        "objet": "question rapide",
        "corps": """\
Bonjour,

Est-ce que la gestion de vos avis Google est geree en interne chez La Maison des Fondues, ou c'est un sujet dont personne ne s'occupe pour l'instant ?

Christopher
Adaptive Logic — Avignon

---
Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Cafe Restaurant La Scene",
        "email": "cafelascene@orange.fr",
        "objet": "question rapide",
        "corps": """\
Bonjour,

Est-ce que quelqu'un gere vos avis Google a La Scene, ou c'est un sujet qui passe a la trappe faute de temps ?

Christopher
Adaptive Logic — Avignon

---
Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Restaurant La Gare",
        "email": "contact@restaurantlagare.net",
        "objet": "question rapide",
        "corps": """\
Bonjour,

Avec 1800+ avis Google, est-ce que quelqu'un s'occupe d'y repondre chez Restaurant La Gare, ou c'est trop de volume pour le faire manuellement ?

Christopher
Adaptive Logic — Avignon

---
Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Fasthotel Avignon Nord",
        "email": "avignon@fasthotel.com",
        "objet": "question rapide",
        "corps": """\
Bonjour,

Est-ce que la gestion des avis Google est geree au niveau de l'hotel ou par le siege chez Fasthotel ? Je cherche a comprendre si c'est un sujet qui vous concerne directement.

Christopher
Adaptive Logic — Avignon

---
Repondez STOP pour ne plus recevoir mes messages.""",
    },
]


def main():
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(SMTP_USER, SMTP_PASS)
    imap.select("Drafts")

    saved = 0
    for p in PROSPECTS:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Christopher \u2014 Adaptive Logic <{SMTP_USER}>"
        msg["To"] = p["email"]
        msg["Subject"] = p["objet"]
        msg["Reply-To"] = SMTP_USER
        msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
        msg.attach(MIMEText(p["corps"], "plain", "utf-8"))

        try:
            imap.append("Drafts", "", None, msg.as_bytes())
            print(f"  OK \u2014 {p['nom']}")
            saved += 1
        except Exception as e:
            print(f"  ERREUR \u2014 {p['nom']}: {e}")

    imap.logout()
    print(f"\n{saved}/4 relances J+7 sauvegardees en brouillon.")


if __name__ == "__main__":
    main()
