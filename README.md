# Export automatisé des présences Skedda

Ce dépôt automatise l’extraction des données de présence provenant d’une table Zapier liée à Skedda.

Un script Python utilisant Playwright ouvre la table Zapier, intercepte les réponses JSON retournées par l’application, transforme les enregistrements et génère le fichier suivant :

```text
Presence_Skedda.csv
```

Un workflow GitHub Actions exécute automatiquement l’export trois fois par jour et publie les changements dans le dépôt.

---

## Fonctionnement général

Le processus automatisé suit les étapes suivantes :

1. GitHub Actions démarre une machine virtuelle Ubuntu.
2. Python 3.12 est installé.
3. Playwright et Chromium sont installés.
4. Le script `main.py` ouvre la table Zapier en mode sans interface graphique.
5. Les réponses JSON de Zapier Tables sont interceptées.
6. Les définitions des champs et les enregistrements sont analysés.
7. Les données sont normalisées et dédoublonnées.
8. Le fichier `Presence_Skedda.csv` est généré.
9. GitHub Actions vérifie si le CSV a changé.
10. Si des changements sont détectés, le fichier est automatiquement publié dans le dépôt.

---

## Structure du dépôt

```text
.
├── .github/
│   └── workflows/
│       └── export-presence-skedda.yml
├── main.py
├── Presence_Skedda.csv
└── README.md
```

### Description des fichiers

| Fichier | Description |
|---|---|
| `main.py` | Script Python qui extrait et transforme les données Zapier |
| `Presence_Skedda.csv` | Résultat de l’extraction |
| `.github/workflows/export-presence-skedda.yml` | Workflow GitHub Actions qui automatise l’exécution |
| `README.md` | Documentation du projet |

---

## Colonnes exportées

Le fichier CSV contient les colonnes suivantes :

| Colonne | Description |
|---|---|
| `Booking ID` | Identifiant unique de la réservation |
| `Date` | Date associée à la réservation |
| `Space IDs` | Identifiants des espaces réservés |
| `Space Names` | Noms des espaces réservés |
| `Start Date` | Date et heure de début |
| `End Date` | Date et heure de fin |
| `Creator ID` | Identifiant de la personne ayant créé la réservation |
| `Creator First Name` | Prénom du créateur |
| `Creator Last Name` | Nom du créateur |
| `Creator Email` | Adresse courriel du créateur |
| `Occurrence Count` | Nombre d’occurrences |
| `Cancelled` | Indique si la réservation est annulée |
| `Cancelled Date` | Date d’annulation |

Le fichier est encodé en `UTF-8 avec BOM`, ce qui facilite son ouverture dans Microsoft Excel et préserve correctement les caractères accentués.

---

## Horaire d’exécution

Le workflow est configuré pour s’exécuter automatiquement tous les jours aux heures suivantes :

- 8 h 50
- 11 h 50
- 14 h 50

Le fuseau horaire configuré dans le workflow est :

```text
America/Toronto
```

Le workflow peut également être lancé manuellement depuis l’onglet **Actions** du dépôt GitHub.

---

## Dépendances

Le projet utilise les technologies suivantes :

- Python 3.12
- Playwright
- Chromium
- GitHub Actions

La seule dépendance Python externe nécessaire est :

```text
playwright
```

---


## Exécution locale

Le script peut également être exécuté localement.

### 1. Cloner le dépôt

```bash
git clone ADRESSE_DU_DEPOT
cd NOM_DU_DEPOT
```

### 2. Créer un environnement virtuel

#### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

#### Linux ou macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Installer Playwright

```bash
python -m pip install --upgrade pip
pip install playwright
python -m playwright install chromium
```

### 4. Définir la variable d’environnement

#### Windows PowerShell

```powershell
$env:ZAPIER_TABLE_URL = "URL_COMPLETE_DE_LA_TABLE_ZAPIER"
```

#### Windows CMD

```cmd
set ZAPIER_TABLE_URL=URL_COMPLETE_DE_LA_TABLE_ZAPIER
```

#### Linux ou macOS

```bash
export ZAPIER_TABLE_URL="URL_COMPLETE_DE_LA_TABLE_ZAPIER"
```

### 5. Exécuter le script

```bash
python main.py
```

Lorsque l’exécution réussit, le fichier suivant est créé ou remplacé :

```text
Presence_Skedda.csv
```

---

## Logique d’extraction

### Capture des réponses réseau

Le script ne se limite pas à lire les éléments visibles dans la page.

Playwright intercepte les réponses JSON provenant de :

```text
tables.zapier.com
```

Le script surveille principalement les réponses dont l’adresse contient :

```text
/fields
```

ou :

```text
/records/query
```

Les réponses `/fields` permettent d’identifier les colonnes de la table.

Les réponses `/records/query` contiennent les enregistrements utilisés pour créer le CSV.

---

## Chargement des lignes

Certaines données peuvent être chargées dynamiquement lorsque la table défile.

Pour forcer leur chargement, le script :

1. ouvre la table Zapier;
2. attend le chargement initial;
3. cherche les éléments défilables dans la page;
4. les déplace vers le bas;
5. répète l’opération plusieurs fois;
6. analyse ensuite toutes les réponses JSON capturées.

Le navigateur Chromium fonctionne en mode sans interface graphique :

```python
HEADLESS = True
```

Cette configuration est nécessaire pour l’exécution dans GitHub Actions.

---

## Correspondance des champs

Zapier peut retourner les champs sous différentes formes, par exemple :

```text
Booking ID
booking_id
fieldId
field_id
f123456
```

Le script normalise les noms de champs en :

- convertissant le texte en minuscules;
- retirant les espaces;
- retirant les caractères spéciaux;
- associant les identifiants techniques Zapier aux colonnes officielles.

Cette logique rend l’extraction plus résistante aux différentes structures JSON retournées par Zapier.

---

## Conversion des valeurs

Le script prend en charge plusieurs types de valeurs :

- texte;
- nombre;
- valeur booléenne;
- liste;
- objet JSON;
- valeur vide.

Les valeurs booléennes sont exportées de la façon suivante :

```text
true
false
```

Les listes sont regroupées dans une seule cellule et séparées par des virgules.

Les objets JSON simples sont convertis en texte lorsque cela est possible.

---

## Tri du résultat

Avant l’écriture du CSV, les données sont triées selon les colonnes suivantes :

1. `Start Date`
2. `Booking ID`

Cela permet de produire un fichier stable et plus facile à consulter.

---

## Workflow GitHub Actions

Le workflow effectue les opérations suivantes :

### Checkout du dépôt

```yaml
uses: actions/checkout@v5
```

### Installation de Python

```yaml
uses: actions/setup-python@v6
```

La version configurée est :

```text
Python 3.12
```

### Installation des dépendances

```bash
python -m pip install --upgrade pip
pip install playwright
```

### Installation de Chromium

```bash
python -m playwright install --with-deps chromium
```

### Exécution de l’export

```bash
python main.py
```

### Vérification du CSV

Le workflow vérifie que le fichier existe :

```bash
test -f Presence_Skedda.csv
```

### Publication du fichier

GitHub Actions ajoute le CSV à Git, puis vérifie si son contenu a changé.

Si aucune modification n’est détectée :

```text
No changes to commit
```

Si une modification est détectée, le workflow crée une publication avec le message suivant :

```text
Update Presence_Skedda.csv
```

Le compte automatisé utilisé est :

```text
github-actions[bot]
````.

