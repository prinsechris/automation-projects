# Stats & Analytics Dashboard — Setup Guide

## Ce qui a ete fait

### 1. Page Notion "Stats & Analytics"
- **URL**: https://www.notion.so/311da200b2d681099fa4ec1f53a93e7d
- **Parent**: Gamified Life Tracker (v2.0)
- **Contenu**: Vue d'ensemble (3 callouts: This Week / This Month / All Time), 4 sections avec placeholders pour les databases, lien retour vers Command Center

### 2. Script Python `create_stats_views.py`
Cree les linked database views avec filtres/tris via l'API interne Notion v3.

**Databases et vues creees:**

| Section | Database | Vues |
|---------|----------|------|
| Activity Log | Activity Log | This Week, This Month, This Year, XP Trend (chart) |
| Daily Summary | Daily Summary | Weekly, Monthly, Yearly |
| Habits | Habits Tracker | Performance (tri Success Rate), By Type (board) |
| Quests & Tasks | Projects & Tasks | Completed, By Category (board), Active |

### 3. Navigation Command Center
- Entree ajoutee dans la database Navigation (Section: Tracking, Order: 5)

## A faire : token_v2

### Etape 1 : Extraire le token
1. Ouvrir https://www.notion.so dans ton navigateur (Chrome/Edge/Firefox)
2. Ouvrir les DevTools : `F12` ou `Ctrl+Shift+I`
3. Aller dans l'onglet **Application** (Chrome) ou **Storage** (Firefox)
4. Cliquer sur **Cookies** > **https://www.notion.so**
5. Chercher le cookie `token_v2`
6. Copier sa valeur (longue chaine de caracteres)

### Etape 2 : Sauvegarder le token
```bash
echo 'COLLER_LE_TOKEN_ICI' > ~/.notion-token
chmod 600 ~/.notion-token
```

### Etape 3 : Tester en dry-run
```bash
cd ~/n8n-workflows
python3 create_stats_views.py --dry-run
```

### Etape 4 : Executer
```bash
python3 create_stats_views.py
```

## Extension n8n (workflow XCoyGKYl0y8r3Geg)

Le workflow "Command Center -- Live Stats" doit etre etendu pour aussi ecrire sur la page Stats & Analytics.

### Modifications a faire dans n8n :

**Nouvelles requetes a ajouter :**
1. **This Month stats** : meme logique que This Week mais filtre date = mois courant
2. **All Time stats** : pas de filtre date, total cumule
3. **Ecriture sur Stats page** : utiliser l'API Notion pour mettre a jour les 3 callouts

**Page Stats ID** : `311da200-b2d6-8109-9fa4-ec1f53a93e7d`

**Callouts a mettre a jour (via replace_content_range ou API interne) :**
- THIS WEEK : XP, Gold, Habits count, Activities count
- THIS MONTH : idem pour le mois
- ALL TIME : Level, XP total, Gold total, Best Streak

**Note** : Le workflow n8n peut utiliser l'API officielle Notion (PATCH pages) pour les proprietes, mais pour le contenu de page il faudra soit l'API interne, soit un node HTTP avec le token_v2.

## Risques et notes
- `token_v2` expire environ tous les 6 mois -- pas critique car le script est one-shot
- L'API interne v3 est stable mais non documentee officiellement
- Si le script echoue : configurer les filtres manuellement dans l'UI Notion (5 min)
- Le chart view (XP Trend) peut necessiter un ajustement manuel dans l'UI
