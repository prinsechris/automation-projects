# Braindump Bot

Bot Telegram de capture et d'evaluation d'idees d'automatisation/business, deploye sur n8n.

## Fonctionnalites

- **Capture texte + vocal** — envoie un message texte ou un vocal, le bot comprend les deux
- **Transcription automatique** — les vocaux sont transcrits via OpenAI Whisper
- **IA conversationnelle** — pose des questions pour clarifier chaque idee
- **Recherche marche** — Google Search (SerpAPI) pour verifier concurrents, demande, prix
- **Scoring qualite /50** — evalue chaque idee sur 5 criteres (utilite, viabilite, commercial, demande, difficulte)
- **Sauvegarde Notion** — sur commande, enregistre l'idee structuree dans une database Notion

## Architecture (15 nodes n8n)

```
Telegram (texte/vocal) → Switch
  → [Vocal] Download → Whisper transcription
  → [Texte] Extract text
       ↓
  BrainDump Agent (GPT-4o-mini)
  + Google Search (SerpAPI)
  + Wikipedia
  + Buffer Memory
       ↓
  Parse Save (Code node)
       ↓
  Save Switch
    → [save] → Notion → Telegram (confirmation)
    → [no save] → Telegram (reponse normale)
```

## Credentials necessaires

| Service | Type n8n | Usage |
|---------|----------|-------|
| Telegram Bot | `telegramApi` | Recevoir/envoyer des messages |
| OpenAI | `openAiApi` | GPT-4o-mini (chat) + Whisper (transcription) |
| Notion | `notionApi` | Ecriture dans la database |
| SerpAPI | `serpApi` | Recherche Google |

## Installation

1. Importer `workflow.json` dans n8n
2. Configurer les credentials (Telegram bot token, OpenAI, Notion, SerpAPI)
3. Partager la database Notion cible avec l'integration n8n
4. Activer le workflow

## Database Notion attendue

La database doit avoir ces proprietes :

| Propriete | Type | Valeurs |
|-----------|------|---------|
| Name | title | Titre de l'idee |
| Description | text | Description detaillee |
| Notes | text | Prochaines etapes |
| Status | select | Idee, En Reflexion, En Cours, Teste, Deployed, Abandonne |
| Type | select | Automatisation, Business Idea, Systeme, Workflow, Client Service |
| Priority | select | Urgent, Important, Normal, Someday |
| Complexity | select | Facile, Moyen, Complexe, Expert |

## Cree le

21 fevrier 2026 — Session 10
