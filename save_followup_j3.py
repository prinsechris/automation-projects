#!/usr/bin/env python3
"""Follow-up J+3 — envoyer le rapport + approbation directement.

A lancer mercredi 5 mars vers 8h.
Sujet en Re: pour threader avec l'email initial.
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
        "objet": "Re: 466 avis, zero reponse ?",
        "corps": """\
Bonjour,

Je vous ai ecrit dimanche au sujet de vos avis Google. J'ai finalise votre diagnostic — voici les resultats :

Diagnostic de votre fiche : https://adaptive-logic.fr/rapports/rapport-reputation-la-maison-des-fondues.html
Exemples de reponses IA sur vos propres avis : https://adaptive-logic.fr/rapports/approbation-la-maison-des-fondues.html

Dites-moi ce que vous en pensez.

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr

---
Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Cafe Restaurant La Scene",
        "email": "cafelascene@orange.fr",
        "objet": "Re: La Scene — 3.7, il suffirait de peu",
        "corps": """\
Bonjour,

Je vous ai ecrit dimanche concernant vos avis Google. J'ai finalise le diagnostic de votre fiche — voici ce que ca donne :

Diagnostic : https://adaptive-logic.fr/rapports/rapport-reputation-cafe-restaurant-la-scene.html
Exemples de reponses IA sur vos propres avis : https://adaptive-logic.fr/rapports/approbation-cafe-restaurant-la-scene.html

Dites-moi ce que vous en pensez.

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr

---
Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Restaurant La Gare",
        "email": "contact@restaurantlagare.net",
        "objet": "Re: 1800 avis — combien vous rapportent vraiment ?",
        "corps": """\
Bonjour,

Je vous ai ecrit dimanche au sujet de vos 1800 avis Google. J'ai finalise votre diagnostic — voici les resultats :

Diagnostic de votre fiche : https://adaptive-logic.fr/rapports/rapport-reputation-restaurant-la-gare.html
Exemples de reponses IA sur vos propres avis : https://adaptive-logic.fr/rapports/approbation-restaurant-la-gare.html

Dites-moi ce que vous en pensez.

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr

---
Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Fasthotel Avignon Nord",
        "email": "avignon@fasthotel.com",
        "objet": "Re: Fasthotel Avignon — 297 avis, 0 reponse",
        "corps": """\
Bonjour,

Je vous ai ecrit dimanche concernant vos avis Google. J'ai finalise le diagnostic de votre fiche :

Diagnostic : https://adaptive-logic.fr/rapports/rapport-reputation-fasthotel-avignon-nord.html
Exemples de reponses IA sur vos propres avis : https://adaptive-logic.fr/rapports/approbation-fasthotel-avignon-nord.html

Dites-moi ce que vous en pensez.

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr

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
    print(f"\n{saved}/4 relances J+3 sauvegardees en brouillon.")


if __name__ == "__main__":
    main()
