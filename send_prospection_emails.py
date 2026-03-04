#!/usr/bin/env python3
"""Send prospection emails via Zoho SMTP — direct, no n8n branding."""

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
        "objet": "Vos 466 avis Google — un levier inexploite",
        "corps": """\
Bonjour,

Je me permets de vous contacter car j'ai remarque quelque chose en analysant votre fiche Google : La Maison des Fondues a 466 avis, mais la grande majorite reste sans reponse.

C'est dommage, parce que ces avis sont un levier enorme pour attirer de nouveaux clients. Google favorise les etablissements qui repondent activement — ca ameliore votre classement local et ca montre aux futurs clients que vous etes a l'ecoute.

Le probleme, c'est que repondre a 466 avis, ca prend un temps fou. Et meme pour les nouveaux avis au quotidien, il faut y penser, trouver les mots, et ne pas faire de copier-coller generique.

C'est exactement pour ca que j'ai cree Review Autopilot : une IA qui repond automatiquement a chaque nouvel avis Google, avec des reponses personnalisees et dans le ton de votre etablissement. Pas de reponses robotiques — chaque reponse est unique et adaptee au contenu de l'avis.

Concretement :
- Reponse automatique a chaque nouvel avis (positif comme negatif)
- Ton personnalise selon votre etablissement
- Vous gardez le controle : validation avant publication si vous le souhaitez
- Installation en moins d'une journee

J'ai d'ailleurs prepare un rapport d'audit gratuit de vos avis Google, ainsi que des exemples de reponses IA adaptees a votre etablissement :

- Rapport d'audit : https://adaptive-logic.fr/rapports/rapport-reputation-la-maison-des-fondues.html
- Exemples de reponses IA : https://adaptive-logic.fr/rapports/approbation-la-maison-des-fondues.html

Si vous etes disponible pour un appel de 10 minutes, je peux vous montrer exactement comment ca fonctionne.

Plus d'infos sur notre site : https://adaptive-logic.fr

Bonne continuation,

Chris
Adaptive Logic — Automatisation IA pour commercants locaux
contact@adaptive-logic.fr
https://adaptive-logic.fr""",
    },
    {
        "nom": "Cafe Restaurant La Scene",
        "email": "cafelascene@orange.fr",
        "objet": "291 avis sans reponse sur Google — on peut changer ca",
        "corps": """\
Bonjour,

En analysant les fiches Google des restaurants d'Avignon, j'ai remarque que le Cafe Restaurant La Scene a accumule 291 avis, avec une note de 3.7/5 — mais quasiment aucune reponse.

C'est un point important, surtout avec une note en dessous de 4 : repondre aux avis (et particulierement aux avis negatifs) est le moyen le plus efficace de remonter votre note. Google le confirme — les etablissements qui repondent regulierement voient leur note moyenne augmenter de 0.1 a 0.3 point en quelques mois.

Pour un restaurant Place Crillon, chaque dixieme de point compte pour convaincre les touristes qui comparent avant de choisir.

J'ai developpe un outil qui s'appelle Review Autopilot : il repond automatiquement a chaque nouvel avis Google avec des reponses personnalisees, dans le ton de votre etablissement. Pas de reponses generiques — chaque reponse est adaptee au contenu de l'avis.

Les avantages concrets :
- Reponse automatique et personnalisee a chaque avis
- Les avis negatifs sont traites avec tact pour desamorcer et montrer votre professionnalisme
- Zero temps a y consacrer de votre cote
- Installation rapide, resultats visibles des les premieres semaines

J'ai d'ailleurs prepare un rapport d'audit gratuit de vos avis Google, ainsi que des exemples de reponses IA adaptees a votre etablissement :

- Rapport d'audit : https://adaptive-logic.fr/rapports/rapport-reputation-cafe-restaurant-la-scene.html
- Exemples de reponses IA : https://adaptive-logic.fr/rapports/approbation-cafe-restaurant-la-scene.html

Si vous etes disponible pour un appel rapide, je peux vous montrer comment ca fonctionne concretement.

Plus d'infos sur notre site : https://adaptive-logic.fr

Bonne continuation,

Chris
Adaptive Logic — Automatisation IA pour commercants locaux
contact@adaptive-logic.fr
https://adaptive-logic.fr""",
    },
    {
        "nom": "Restaurant La Gare",
        "email": "contact@restaurantlagare.net",
        "objet": "1800+ avis en ligne — et si chaque reponse vous ramenait des clients ?",
        "corps": """\
Bonjour,

En faisant une analyse des restaurants du Grand Avignon, Restaurant La Gare m'a immediatement interpelle : plus de 1800 avis en ligne, c'est enorme. Tres peu d'etablissements atteignent ce volume.

Mais j'ai aussi remarque que la majorite de ces avis restent sans reponse. Sur un volume pareil, c'est une mine d'or inexploitee. Chaque reponse a un avis est une opportunite de :
- Montrer aux futurs clients que vous etes a l'ecoute
- Desamorcer les avis negatifs avec professionnalisme
- Ameliorer votre classement Google (l'algorithme favorise les etablissements reactifs)

Evidemment, repondre a 1800 avis c'est impossible manuellement. C'est pour ca que j'ai cree Review Autopilot : une IA qui repond automatiquement a chaque nouvel avis, avec des reponses personnalisees — pas du copier-coller.

L'outil s'adapte au ton de votre etablissement et traite les avis negatifs avec tact. Vous pouvez valider chaque reponse avant publication si vous le souhaitez.

J'ai d'ailleurs prepare un rapport d'audit gratuit de vos avis, ainsi que des exemples de reponses IA adaptees a votre etablissement :

- Rapport d'audit : https://adaptive-logic.fr/rapports/rapport-reputation-restaurant-la-gare.html
- Exemples de reponses IA : https://adaptive-logic.fr/rapports/approbation-restaurant-la-gare.html

Si vous etes disponible pour un appel de 10 minutes, je peux vous expliquer comment ca marche concretement.

Plus d'infos : https://adaptive-logic.fr

Bonne continuation,

Chris
Adaptive Logic — Automatisation IA pour commercants locaux
contact@adaptive-logic.fr
https://adaptive-logic.fr""",
    },
    {
        "nom": "Fasthotel Avignon Nord",
        "email": "avignon@fasthotel.com",
        "objet": "Vos 297 avis Google sans reponse — un impact direct sur vos reservations",
        "corps": """\
Bonjour,

Je me permets de vous contacter car j'ai analyse la fiche Google de Fasthotel Avignon Nord : 297 avis avec une note de 3.7/5, et quasiment aucune reponse.

Pour un hotel, les avis Google sont un facteur de decision majeur. Les voyageurs comparent systematiquement les notes et les reponses avant de reserver. Un hotel qui repond a ses avis envoie un signal fort : "nous prenons soin de nos clients".

Les etudes montrent que les hotels qui repondent activement a leurs avis voient leur taux de reservation augmenter et leur note remonter progressivement — surtout quand les avis negatifs sont traites avec professionnalisme.

J'ai developpe Review Autopilot, un outil qui repond automatiquement a chaque nouvel avis Google avec des reponses personnalisees et adaptees au ton de votre etablissement. Pas de reponses generiques — chaque reponse est unique.

Concretement :
- Reponse automatique a chaque nouvel avis
- Traitement professionnel des avis negatifs
- Zero temps a y consacrer
- Installation en moins d'une journee

J'ai d'ailleurs prepare un rapport d'audit gratuit de vos avis Google, ainsi que des exemples de reponses IA adaptees a votre etablissement :

- Rapport d'audit : https://adaptive-logic.fr/rapports/rapport-reputation-fasthotel-avignon-nord.html
- Exemples de reponses IA : https://adaptive-logic.fr/rapports/approbation-fasthotel-avignon-nord.html

Si vous etes disponible pour un appel rapide, je peux vous montrer comment ca fonctionne concretement.

Plus d'infos sur notre site : https://adaptive-logic.fr

Bonne continuation,

Chris
Adaptive Logic — Automatisation IA pour commercants locaux
contact@adaptive-logic.fr
https://adaptive-logic.fr""",
    },
]


def send_email(prospect: dict) -> bool:
    """Send one prospection email via Zoho SMTP."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"Chris — Adaptive Logic <{SMTP_USER}>"
    msg["To"] = prospect["email"]
    msg["Subject"] = prospect["objet"]
    msg["Reply-To"] = SMTP_USER

    # Plain text
    msg.attach(MIMEText(prospect["corps"], "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"  OK — {prospect['nom']} ({prospect['email']})")
        return True
    except Exception as e:
        print(f"  ERREUR — {prospect['nom']}: {e}")
        return False


def main():
    print(f"Envoi de {len(PROSPECTS)} emails via {SMTP_USER}...\n")
    sent = 0
    for p in PROSPECTS:
        if send_email(p):
            sent += 1
    print(f"\n{sent}/{len(PROSPECTS)} emails envoyes.")


if __name__ == "__main__":
    main()
