#!/usr/bin/env python3
"""Save optimized prospection emails v3 — final version."""

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
        "objet": "La Maison des Fondues \u2014 vos avis Google",
        "corps": """\
Bonjour,

466 avis Google pour La Maison des Fondues, 3.8 de note, et quasiment zero reponse. C'est un levier enorme qui dort.

Les commerces qui repondent a leurs avis gagnent en moyenne +0.3 etoile en 3 mois. Rue Bonneterie, ca veut dire plus de touristes qui poussent la porte au lieu de passer devant.

J'ai cree un outil qui repond automatiquement a chaque nouvel avis, dans votre ton, en 24h. Je cherche 3 restaurants pilotes a Avignon pour le deployer.

Ca vous parle ?

Chris
Adaptive Logic \u2014 Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Cafe Restaurant La Scene",
        "email": "cafelascene@orange.fr",
        "objet": "La Scene \u2014 vos avis Google",
        "corps": """\
Bonjour,

291 avis Google, 3.7/5, zero reponse. Place Crillon, quand un touriste compare deux restaurants, chaque dixieme de point fait la difference.

Repondre aux avis — surtout les negatifs — est le moyen le plus rapide de remonter une note sous 4. Les etablissements qui le font gagnent +0.3 etoile en quelques mois.

J'ai cree un outil qui genere des reponses personnalisees a chaque avis automatiquement. Je cherche 3 restaurants pilotes a Avignon.

C'est un sujet pour vous en ce moment ?

Chris
Adaptive Logic \u2014 Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Restaurant La Gare",
        "email": "contact@restaurantlagare.net",
        "objet": "Restaurant La Gare \u2014 1800 avis",
        "corps": """\
Bonjour,

1800+ avis en ligne pour Restaurant La Gare, c'est enorme. Tres peu d'etablissements atteignent ce volume. Mais la majorite reste sans reponse.

Chaque avis sans reponse, c'est un futur client qui se dit "ils s'en fichent". Google penalise aussi les fiches inactives dans le classement local.

J'ai cree un outil qui repond automatiquement a chaque avis, avec des reponses personnalisees — pas du copier-coller. Je cherche 3 restaurants pilotes dans le Grand Avignon.

Ca vaut 10 minutes pour en discuter ?

Chris
Adaptive Logic \u2014 Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Fasthotel Avignon Nord",
        "email": "avignon@fasthotel.com",
        "objet": "Fasthotel Avignon Nord \u2014 vos avis",
        "corps": """\
Bonjour,

297 avis Google, 3.7/5, quasiment aucune reponse. Pour un hotel, c'est critique : les voyageurs lisent les avis ET les reponses avant de reserver.

Un hotel qui repond a ses avis envoie un signal fort. Les etudes montrent que ca augmente directement le taux de reservation et fait remonter la note.

J'ai cree un outil qui repond a chaque avis automatiquement, dans le ton de votre etablissement. Je cherche 3 hotels pilotes dans le Vaucluse.

C'est un sujet pour vous ?

Chris
Adaptive Logic \u2014 Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
]


def main():
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(SMTP_USER, SMTP_PASS)

    # Delete old drafts
    imap.select("Drafts")
    status, data = imap.search(None, "ALL")
    old_ids = data[0].split()
    for uid in old_ids:
        imap.store(uid, "+FLAGS", "\\Deleted")
    imap.expunge()
    print(f"Anciens brouillons supprimes: {len(old_ids)}")

    # Save new drafts
    saved = 0
    for p in PROSPECTS:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Chris \u2014 Adaptive Logic <{SMTP_USER}>"
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
    print(f"\n{saved}/4 brouillons v3 sauvegardes. Les anciens sont supprimes.")


if __name__ == "__main__":
    main()
