#!/usr/bin/env python3
"""Send prospection emails v4 via Zoho SMTP — direct send."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = "smtp.zoho.eu"
SMTP_PORT = 465
SMTP_USER = "contact@adaptive-logic.fr"
SMTP_PASS = "PJe4ad!NGjqhY8C5"

PROSPECTS = [
    {
        "nom": "La Maison des Fondues",
        "email": "maisondesfonduesavignon@gmail.com",
        "objet": "466 avis, zero reponse ?",
        "corps": """\
Bonjour,

466 avis Google pour La Maison des Fondues, 3.8 de note \u2014 et des avis negatifs recents sans aucune reponse. Rue Bonneterie, les touristes comparent sur Google avant de pousser la porte.

Chaque avis negatif ignore fait fuir jusqu'a 30 clients potentiels. Sur votre volume, ca peut representer plusieurs centaines d'euros par mois de manque a gagner.

Je gere les reponses aux avis automatiquement pour les commercants d'Avignon. J'ai prepare un diagnostic gratuit de votre fiche \u2014 je vous l'envoie ?

Christopher
Adaptive Logic \u2014 Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Cafe Restaurant La Scene",
        "email": "cafelascene@orange.fr",
        "objet": "La Scene \u2014 3.7, il suffirait de peu",
        "corps": """\
Bonjour,

Place Crillon, les touristes comparent 4-5 restaurants en 30 secondes sur Google avant de choisir. La Scene a 291 avis a 3.7/5 \u2014 aucune reponse, meme sur les negatifs.

Passer de 3.7 a 4.0, c'est le seuil ou Google vous met en avant dans les resultats locaux. Les etablissements qui repondent a leurs avis y arrivent en 3 mois.

Je gere ca automatiquement pour les restaurants du centre-ville. J'ai prepare un diagnostic de votre fiche \u2014 ca vous interesse de le recevoir ?

Christopher
Adaptive Logic \u2014 Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Restaurant La Gare",
        "email": "contact@restaurantlagare.net",
        "objet": "1800 avis \u2014 combien vous rapportent vraiment ?",
        "corps": """\
Bonjour,

1800+ avis pour Restaurant La Gare, c'est un capital enorme \u2014 tres peu d'etablissements dans le Grand Avignon atteignent ce volume. Mais les avis negatifs recents restent sans reponse, et Google penalise les fiches inactives dans le classement local.

Chaque avis negatif ignore fait fuir jusqu'a 30 futurs clients. Sur 1800 avis, meme une poignee sans reponse represente des milliers d'euros de manque a gagner par an.

Je gere les reponses automatiquement \u2014 chaque avis recoit une reponse personnalisee dans votre ton, en 24h. J'ai prepare un diagnostic de votre fiche \u2014 je vous l'envoie ?

Christopher
Adaptive Logic \u2014 Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
    {
        "nom": "Fasthotel Avignon Nord",
        "email": "avignon@fasthotel.com",
        "objet": "Fasthotel Avignon \u2014 297 avis, 0 reponse",
        "corps": """\
Bonjour,

Sur Google, les voyageurs lisent les avis ET les reponses de la direction avant de reserver. Fasthotel Avignon Nord a 297 avis a 3.7/5 \u2014 quasiment aucune reponse, meme sur les plaintes.

Pour un hotel budget, chaque dixieme de point compte : les clients comparent au centime pres. Un hotel qui repond a ses avis remonte sa note de +0.3 en 3 mois et augmente son taux de reservation.

Je gere les reponses aux avis automatiquement pour les hotels du Vaucluse. J'ai analyse votre fiche \u2014 je vous envoie le diagnostic ?

Christopher
Adaptive Logic \u2014 Avignon
contact@adaptive-logic.fr

---
Email envoye car votre etablissement est reference sur Google Maps. Repondez STOP pour ne plus recevoir mes messages.""",
    },
]


def main():
    print(f"Connexion SMTP a Zoho ({SMTP_USER})...")
    sent = 0
    for p in PROSPECTS:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Christopher \u2014 Adaptive Logic <{SMTP_USER}>"
        msg["To"] = p["email"]
        msg["Subject"] = p["objet"]
        msg["Reply-To"] = SMTP_USER
        msg.attach(MIMEText(p["corps"], "plain", "utf-8"))

        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            print(f"  ENVOYE \u2014 {p['nom']} ({p['email']})")
            sent += 1
        except Exception as e:
            print(f"  ERREUR \u2014 {p['nom']}: {e}")

    print(f"\n{sent}/4 emails envoyes.")


if __name__ == "__main__":
    main()
