#!/usr/bin/env python3
"""Save optimized prospection emails v4 — audit-corrected version.

Changes from v3:
- Subject lines: curiosity/tension format (questions, chiffres choc)
- CTA: rapport gratuit as lead magnet (interest-based, not time-based)
- Agitation: concrete impact in euros/clients lost
- "je gere ca" instead of "j'ai cree un outil"
- Signature: Christopher (not Chris)
- RGPD footer kept
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
        "objet": "466 avis, zero reponse ?",
        "corps": """\
Bonjour,

466 avis Google pour La Maison des Fondues, 3.8 de note — et des avis negatifs recents sans aucune reponse. Rue Bonneterie, les touristes comparent sur Google avant de pousser la porte.

Chaque avis negatif ignore fait fuir jusqu'a 30 clients potentiels. Sur votre volume, ca peut representer plusieurs centaines d'euros par mois de manque a gagner.

Je gere les reponses aux avis automatiquement pour les commercants d'Avignon. J'ai prepare un diagnostic gratuit de votre fiche — je vous l'envoie ?

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Cafe Restaurant La Scene",
        "email": "cafelascene@orange.fr",
        "objet": "La Scene — 3.7, il suffirait de peu",
        "corps": """\
Bonjour,

Place Crillon, les touristes comparent 4-5 restaurants en 30 secondes sur Google avant de choisir. La Scene a 291 avis a 3.7/5 — aucune reponse, meme sur les negatifs.

Passer de 3.7 a 4.0, c'est le seuil ou Google vous met en avant dans les resultats locaux. Les etablissements qui repondent a leurs avis y arrivent en 3 mois.

Je gere ca automatiquement pour les restaurants du centre-ville. J'ai prepare un diagnostic de votre fiche — ca vous interesse de le recevoir ?

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Restaurant La Gare",
        "email": "contact@restaurantlagare.net",
        "objet": "1800 avis — combien vous rapportent vraiment ?",
        "corps": """\
Bonjour,

1800+ avis pour Restaurant La Gare, c'est un capital enorme — tres peu d'etablissements dans le Grand Avignon atteignent ce volume. Mais les avis negatifs recents restent sans reponse, et Google penalise les fiches inactives dans le classement local.

Chaque avis negatif ignore fait fuir jusqu'a 30 futurs clients. Sur 1800 avis, meme une poignee sans reponse represente des milliers d'euros de manque a gagner par an.

Je gere les reponses automatiquement — chaque avis recoit une reponse personnalisee dans votre ton, en 24h. J'ai prepare un diagnostic de votre fiche — je vous l'envoie ?

Christopher
Adaptive Logic — Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Fasthotel Avignon Nord",
        "email": "avignon@fasthotel.com",
        "objet": "Fasthotel Avignon — 297 avis, 0 reponse",
        "corps": """\
Bonjour,

Sur Google, les voyageurs lisent les avis ET les reponses de la direction avant de reserver. Fasthotel Avignon Nord a 297 avis a 3.7/5 — quasiment aucune reponse, meme sur les plaintes.

Pour un hotel budget, chaque dixieme de point compte : les clients comparent au centime pres. Un hotel qui repond a ses avis remonte sa note de +0.3 en 3 mois et augmente son taux de reservation.

Je gere les reponses aux avis automatiquement pour les hotels du Vaucluse. J'ai analyse votre fiche — je vous envoie le diagnostic ?

Christopher
Adaptive Logic — Avignon
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
    print(f"\n{saved}/4 brouillons v4 sauvegardes. Les anciens sont supprimes.")


if __name__ == "__main__":
    main()
