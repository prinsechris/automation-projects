# Base de Competences — Chris / Adaptive Logic

> Derniere mise a jour : 2026-02-23
> Source : session logs des 3 repos + projets deployes

---

## 1. Automatisation n8n

| Competence | Niveau | Preuves |
|------------|--------|---------|
| Workflows multi-nodes (15+ nodes) | Avance | Braindump Bot (15 nodes), Manager Agent (16 nodes) |
| LangChain Agents (toolWorkflow, Agent node) | Avance | Manager v3 : orchestrateur multi-agent avec chainage |
| Triggers (Telegram, Schedule, Webhook, Execute) | Avance | Workflows cron (Morning Brief, Weekly), webhook Telegram |
| Integration Notion API | Avance | CRUD Goals/Tasks/Decisions, scoring WICE automatise |
| Integration Telegram Bot API | Avance | 2 bots (Braindump + Orun), voice + text, HTML formatting |
| OpenAI Whisper (transcription vocale) | Intermediaire | Pipeline voice dans Manager v2/v3 |
| SerpAPI + Wikipedia (recherche web) | Intermediaire | Web Search sub-workflow |
| Switch/Router/Classifier | Avance | Manager v2 (7 branches), Braindump Bot (save detection) |
| Deploiement API n8n (create/activate/delete workflows) | Avance | Script Python 3000+ lignes, deploiement automatise complet |
| Buffer Memory / Postgres Memory LangChain | Intermediaire | Window Buffer 40 msgs dans Manager v3 |

---

## 2. Intelligence Artificielle

| Competence | Niveau | Preuves |
|------------|--------|---------|
| Claude Code CLI (Opus/Sonnet) | Expert | Outil principal de dev, sessions 1-10+, dictee vocale via Terminus |
| Prompt engineering (system prompts complexes) | Avance | Prompts multi-sections pour 7 sous-agents + orchestrateur |
| Anthropic API (Claude Sonnet 4.5) | Avance | Integration directe dans n8n, nodes LangChain |
| OpenAI API (GPT-4o-mini, Whisper, TTS) | Intermediaire | Braindump Bot, pipeline video TikTok |
| Agents multi-outils (LangChain pattern) | Avance | Manager v3 : 7 tools, chainage autonome, synthese croisee |
| Architecture multi-agent | Avance | Systeme strategique 3 couches (Notion + n8n + Claude subagents) |

---

## 3. Web Scraping & Data

| Competence | Niveau | Preuves |
|------------|--------|---------|
| Reddit scraping (universal scraper) | Avance | Multi-niche, filtrage pertinence, cross-post detection |
| API REST custom (FastAPI) | Intermediaire | Endpoints SpillBox : /scrape, /production, /full pipeline |
| Jina AI Reader (URL → markdown) | Debutant | Sub-workflow deploye, a tester |
| SerpAPI (Google Search) | Intermediaire | Integre dans Web Search + Braindump Bot |
| Notion comme base de donnees | Avance | 3 DBs (Goals, Tasks, Decisions), requetes filtrees |

---

## 4. Production Video (TikTok)

| Competence | Niveau | Preuves |
|------------|--------|---------|
| Pipeline video automatise | Avance | Scrape → Generate → Render → Upload (full auto) |
| FFmpeg (sous-titres, montage) | Intermediaire | Fredoka One, ombre portee, qualite optimisee |
| TTS (Text-to-Speech) | Intermediaire | Vitesse dynamique, pauses reduites |
| Multi-niche system (configs JSON) | Intermediaire | SpillBox (drama/cheating), extensible |
| Dropbox integration | Intermediaire | Upload/download stories automatise |
| n8n workflow scheduling (production toutes les 8h) | Intermediaire | Workflow SpillBox Auto-Production |

---

## 5. Infrastructure & DevOps

| Competence | Niveau | Preuves |
|------------|--------|---------|
| Hostinger VPS (n8n cloud) | Intermediaire | Instance n8n production avec 50+ workflows |
| Serveur custom (31.97.54.26) | Intermediaire | API SpillBox, scraping endpoints |
| GitHub (repos, branches, gh CLI) | Avance | 3 repos, branches multiples, deploiement via gh CLI |
| Python scripting | Avance | Script deploiement n8n (3000+ lignes), scrapers |
| JavaScript (n8n Code nodes) | Intermediaire | Formatage HTML, parsing JSON, aggregation donnees |
| PostgreSQL | Debutant | Base n8n interne, memory TBD |

---

## 6. Business & Strategie

| Competence | Niveau | Preuves |
|------------|--------|---------|
| Analyse concurrentielle | Avance | 18 agences analysees, 6 gaps identifies |
| Pricing packages | Avance | 3 packages (890/2900/7500 EUR), marges calculees |
| Analyse marche local (Avignon) | Intermediaire | 1300 commerces, 800 hyper-centre, scoring systemes |
| Systeme de scoring (WICE) | Intermediaire | Scoring automatise des objectifs via Notion |
| Decision logging | Intermediaire | Decision Log Notion avec learnings |
| Prospection TPE/PME | Debutant | Scout v2 deploye, a activer sur le terrain |

---

## 7. Outils & Environnement

| Outil | Usage |
|-------|-------|
| Claude Code CLI (Opus 4.6) | Dev principal, architecture, deploiement |
| Terminus | Terminal mobile/desktop avec dictee vocale |
| n8n (self-hosted Hostinger) | Orchestration workflows, agents, automations |
| Notion | Base de donnees strategique (Goals, Tasks, Decisions) |
| Telegram | Interface utilisateur (bots Braindump + Orun) |
| GitHub (gh CLI) | Versioning, collaboration, deploiement |
| Anthropic API | LLM principal (Claude Sonnet 4.5) |
| OpenAI API | Whisper (transcription), GPT-4o-mini (braindump) |
| SerpAPI | Recherche Google programmatique |
| Jina AI | Web scraping (URL → markdown) |
| Dropbox | Stockage videos TikTok |
| FFmpeg | Rendering video |

---

## Evolution prevue

- [ ] Postgres Chat Memory (memoire persistante cross-session)
- [ ] Scraper custom (31.97.54.26) integre dans Orun
- [ ] Review Autopilot : premier client payant
- [ ] Deploiement site vitrine (HTML custom ou Framer)
- [ ] Premier client Avignon via prospection directe
