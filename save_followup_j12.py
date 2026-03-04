#!/usr/bin/env python3
"""Follow-up J+12 — breakup email (dernier contact).

A lancer vendredi 14 mars vers 8h.
Le breakup email cree de l'urgence par la perte.
Souvent le mail avec le meilleur taux de reponse de la sequence.
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
        "objet": "je ferme le dossier ?",
        "corps": """\
Bonjour,

Je vous ai contacte il y a deux semaines au sujet de vos avis Google. Pas de reponse, je comprends — le quotidien d'un restaurant ne laisse pas beaucoup de temps.

J'ai garde votre diagnostic sous le coude. Si c'est un sujet un jour, vous savez ou me trouver.

Bonne continuation,

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr""",
    },
    {
        "nom": "Cafe Restaurant La Scene",
        "email": "cafelascene@orange.fr",
        "objet": "je ferme le dossier ?",
        "corps": """\
Bonjour,

Je vous ai ecrit il y a deux semaines concernant vos avis Google a La Scene. Je n'ai pas eu de retour — je comprends tout a fait, le service ne s'arrete pas.

Votre diagnostic est pret si le sujet vous interesse un jour. N'hesitez pas a me recontacter.

Bonne continuation,

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr""",
    },
    {
        "nom": "Restaurant La Gare",
        "email": "contact@restaurantlagare.net",
        "objet": "je ferme le dossier ?",
        "corps": """\
Bonjour,

Je vous ai contacte il y a deux semaines au sujet de vos 1800 avis Google. Pas de retour — je comprends, la restauration ne laisse pas beaucoup de repit.

Le diagnostic de votre fiche est toujours disponible si ca vous interesse un jour. Vous savez ou me trouver.

Bonne continuation,

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr""",
    },
    {
        "nom": "Fasthotel Avignon Nord",
        "email": "avignon@fasthotel.com",
        "objet": "je ferme le dossier ?",
        "corps": """\
Bonjour,

Je vous ai ecrit il y a deux semaines concernant la gestion de vos avis Google. Pas de retour de votre part.

Je garde votre diagnostic sous le coude — si le sujet devient une priorite, n'hesitez pas a me recontacter.

Bonne continuation,

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr""",
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
    print(f"\n{saved}/4 breakup emails J+12 sauvegardes en brouillon.")


if __name__ == "__main__":
    main()
