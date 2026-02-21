# Automation Projects — Adaptive Logic

Collection de projets d'automatisation : workflows n8n, bots Telegram, integrations IA.

## Projets

| Projet | Description | Status |
|--------|-------------|--------|
| [Braindump Bot](braindump-bot/) | Bot Telegram de capture et evaluation d'idees avec IA + Notion | Operationnel |

## Stack technique

- **n8n** — orchestration des workflows (self-hosted)
- **Telegram Bot API** — interface utilisateur
- **OpenAI** — GPT-4o-mini (chat) + Whisper (transcription vocale)
- **SerpAPI** — recherche Google en temps reel
- **Notion API** — stockage structure des donnees

## Structure

```
automation-projects/
  braindump-bot/          # Bot Telegram capture d'idees
    README.md             # Documentation du projet
    workflow.json          # Export du workflow n8n
  [futur-projet]/         # Prochains projets
```

## Auteur

**Adaptive Logic** — Agence d'automatisation IA, Avignon
