#!/usr/bin/env python3
"""Save optimized prospection emails as drafts in Zoho Mail via IMAP.

v2 — Based on cold email best practices:
- 50-120 words max
- Plain text, zero links in body
- Simple CTA (question ouverte)
- RGPD compliant (mention desinscription)
- Reports saved for follow-up emails (J+3)
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
        "objet": "La Maison des Fondues \u2014 vos avis Google",
        "corps": """\
Bonjour,

J'ai regarde vos avis Google ce matin. La Maison des Fondues a 466 avis, avec une note de 3.8/5, mais quasiment aucune reponse.

Un commerce qui repond a ses avis gagne en moyenne +0.3 etoile en 3 mois. A Avignon intra-muros, ca fait la difference entre un touriste qui entre et un qui passe devant.

J'ai un systeme IA qui repond automatiquement a chaque avis, dans votre ton, en 24h. Je cherche 3 restaurants pilotes a Avignon pour le tester.

Ca vous parle ?

Chris
Adaptive Logic \u2014 Automatisation IA pour commercants
contact@adaptive-logic.fr

---
Vous recevez cet email car votre etablissement est reference sur Google Maps. Pour ne plus recevoir mes messages, repondez STOP.""",
    },
    {
        "nom": "Cafe Restaurant La Scene",
        "email": "cafelascene@orange.fr",
        "objet": "La Scene \u2014 vos avis Google",
        "corps": """\
Bonjour,

J'ai analyse vos avis Google : Cafe Restaurant La Scene a 291 avis, 3.7/5, et zero reponse.

Avec une note sous 4, repondre aux avis (surtout les negatifs) est le levier le plus rapide pour remonter. Les etablissements qui repondent regulierement gagnent +0.3 etoile en quelques mois.

Place Crillon, chaque dixieme de point compte pour les touristes qui comparent.

J'ai un systeme IA qui repond a chaque avis automatiquement, dans votre ton. Je cherche 3 restaurants pilotes a Avignon.

C'est un sujet pour vous en ce moment ?

Chris
Adaptive Logic \u2014 Automatisation IA pour commercants
contact@adaptive-logic.fr

---
Vous recevez cet email car votre etablissement est reference sur Google Maps. Pour ne plus recevoir mes messages, repondez STOP.""",
    },
    {
        "nom": "Restaurant La Gare",
        "email": "contact@restaurantlagare.net",
        "objet": "Restaurant La Gare \u2014 vos 1800 avis",
        "corps": """\
Bonjour,

Restaurant La Gare a plus de 1800 avis en ligne. C'est enorme, tres peu d'etablissements atteignent ce volume.

Mais la majorite reste sans reponse. Sur un volume pareil, c'est une mine d'or inexploitee. Google favorise les etablissements reactifs, et chaque reponse montre aux futurs clients que vous etes a l'ecoute.

Evidemment, repondre a 1800 avis c'est impossible manuellement. J'ai un systeme IA qui le fait automatiquement, avec des reponses personnalisees.

Ca vaut 10 minutes de votre temps pour en discuter ?

Chris
Adaptive Logic \u2014 Automatisation IA pour commercants
contact@adaptive-logic.fr

---
Vous recevez cet email car votre etablissement est reference sur Google Maps. Pour ne plus recevoir mes messages, repondez STOP.""",
    },
    {
        "nom": "Fasthotel Avignon Nord",
        "email": "avignon@fasthotel.com",
        "objet": "Fasthotel Avignon Nord \u2014 vos avis Google",
        "corps": """\
Bonjour,

J'ai regarde la fiche Google de Fasthotel Avignon Nord : 297 avis, 3.7/5, et quasiment aucune reponse.

Pour un hotel, les avis sont le premier reflexe des voyageurs avant de reserver. Un hotel qui repond a ses avis envoie un signal fort : "nous prenons soin de nos clients". Les etudes montrent que ca augmente directement le taux de reservation.

J'ai un systeme IA qui repond automatiquement a chaque avis, dans le ton de votre etablissement. Positifs comme negatifs.

C'est un sujet pour vous ?

Chris
Adaptive Logic \u2014 Automatisation IA pour commercants
contact@adaptive-logic.fr

---
Vous recevez cet email car votre etablissement est reference sur Google Maps. Pour ne plus recevoir mes messages, repondez STOP.""",
    },
]


def save_draft(imap_conn, prospect: dict) -> bool:
    """Save one email as draft in Zoho via IMAP."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"Chris \u2014 Adaptive Logic <{SMTP_USER}>"
    msg["To"] = prospect["email"]
    msg["Subject"] = prospect["objet"]
    msg["Reply-To"] = SMTP_USER
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    msg.attach(MIMEText(prospect["corps"], "plain", "utf-8"))

    try:
        imap_conn.append("Drafts", "", None, msg.as_bytes())
        print(f"  OK \u2014 {prospect['nom']} ({prospect['email']})")
        return True
    except Exception as e:
        print(f"  ERREUR \u2014 {prospect['nom']}: {e}")
        return False


def main():
    print(f"Connexion IMAP a Zoho ({SMTP_USER})...")
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(SMTP_USER, SMTP_PASS)
    print("Connecte.\n")

    print(f"Sauvegarde de {len(PROSPECTS)} brouillons v2...\n")
    saved = 0
    for p in PROSPECTS:
        if save_draft(imap, p):
            saved += 1

    imap.logout()
    print(f"\n{saved}/{len(PROSPECTS)} brouillons sauvegardes.")
    print("Les anciens brouillons sont encore la \u2014 supprime-les manuellement.")
    print("\nSTRATEGIE DE RELANCE (J+3) :")
    print("  Email 2 : nouvel angle + lien vers le rapport d'audit")
    print("  Email 3 (J+7) : extrait du rapport + offre de l'envoyer")
    print("  Email 4 (J+12) : breakup email ('je ferme le dossier ?')")


if __name__ == "__main__":
    main()
