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

## Configuration du GitHub Secret

L’adresse de la table Zapier ne doit pas être inscrite directement dans le code.

Elle est fournie au script au moyen du GitHub Secret suivant :

```text
ZAPIER_TABLE_URL
```

### Création du secret

Dans le dépôt GitHub :

1. Ouvrir **Settings**.
2. Sélectionner **Secrets and variables**.
3. Sélectionner **Actions**.
4. Cliquer sur **New repository secret**.
5. Utiliser le nom suivant :

```text
ZAPIER_TABLE_URL
```

6. Inscrire comme valeur l’URL complète permettant d’accéder à la table Zapier.
7. Enregistrer le secret.

Le workflow transmet cette valeur au script comme variable d’environnement :

```yaml
env:
  ZAPIER_TABLE_URL: ${{ secrets.ZAPIER_TABLE_URL }}
```

Le script récupère ensuite cette valeur avec :

```python
ZAPIER_URL = os.environ.get("ZAPIER_TABLE_URL")
```

Si le secret est absent, le script termine immédiatement avec une erreur.

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

## Règles de dédoublonnage

La logique de dédoublonnage dépend du contenu de la colonne `Booking ID`.

### Booking ID normal

Pour un identifiant standard, une seule ligne est conservée par `Booking ID`.

Exemple :

```text
123456
```

Si plusieurs versions du même enregistrement sont trouvées, le script conserve celle qui contient le plus grand nombre de colonnes reconnues.

### Booking ID commençant par `Ex`

Toutes les lignes dont le `Booking ID` commence par `Ex` sont conservées, même lorsque plusieurs lignes possèdent le même identifiant.

Exemples :

```text
Ex123456
EX123456
ex123456
```

La comparaison n’est pas sensible aux majuscules et minuscules.

### Booking ID vide

Les lignes sans `Booking ID` sont d’abord comparées selon l’ensemble de leurs colonnes.

Avant la création du CSV, toutes les lignes dont le `Booking ID` est vide sont toutefois retirées.

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
```

---

## Exécution manuelle du workflow

Pour lancer l’export manuellement :

1. ouvrir le dépôt GitHub;
2. sélectionner l’onglet **Actions**;
3. sélectionner le workflow **Export Presence Skedda**;
4. cliquer sur **Run workflow**;
5. sélectionner la branche désirée;
6. cliquer sur **Run workflow**.

L’exécution manuelle utilise le déclencheur suivant :

```yaml
workflow_dispatch:
```

---

## Vérification des exécutions

Les journaux du workflow affichent notamment :

- le type de déclenchement;
- l’horaire ayant déclenché le workflow;
- l’heure UTC;
- l’heure de Toronto;
- la version de Python;
- le nombre de réponses Zapier capturées;
- le nombre de champs reconnus;
- le nombre de lignes exportées;
- le nombre de colonnes;
- l’emplacement du CSV;
- la date et l’heure de l’exécution.

Exemple de résultat :

```text
============================================================
EXPORT TERMINÉ
============================================================
Lignes : 784
Colonnes : 13
CSV : /chemin/du/depot/Presence_Skedda.csv
Exécution : 2026-10-26 08:50:00
```

Le nombre de lignes dépend du contenu de la table au moment de l’exécution.

---

## Gestion des erreurs

Le script retourne une erreur dans les situations suivantes.

### Secret absent

```text
ERREUR : GitHub Secret 'ZAPIER_TABLE_URL' absent.
```

Vérifier que le secret existe dans les paramètres du dépôt et que son nom est exactement :

```text
ZAPIER_TABLE_URL
```

### Aucune ligne trouvée

```text
ERREUR : aucune ligne trouvée.
```

Causes possibles :

- l’URL Zapier n’est plus valide;
- la table n’est pas accessible;
- aucune réponse `/records/query` n’a été interceptée;
- la structure des réponses Zapier a changé;
- le temps de chargement est insuffisant;
- les champs attendus ne correspondent plus aux champs de la table.

### Fichier CSV absent

Si `Presence_Skedda.csv` n’est pas créé, l’étape `Verify CSV` échoue automatiquement.

### Erreur pendant la publication Git

Une erreur à l’étape `Commit CSV` peut notamment survenir si :

- le workflow n’a pas la permission d’écrire dans le dépôt;
- la branche est protégée;
- une règle du dépôt interdit les publications directes;
- un autre processus a modifié la branche pendant l’exécution.

Le workflow utilise la permission suivante :

```yaml
permissions:
  contents: write
```

---

## Paramètres configurables

Les principaux paramètres sont définis au début de `main.py`.

### Identifiant de la table

```python
TABLE_ID = "01M4XMP5Q9SG9RP6X9BY8A8SHA"
```

### Nom du fichier de sortie

```python
OUTPUT_FILE = SCRIPT_FOLDER / "Presence_Skedda.csv"
```

### Mode sans interface graphique

```python
HEADLESS = True
```

### Délai maximal de chargement

```python
PAGE_TIMEOUT_MS = 120_000
```

### Attente après le chargement initial

```python
WAIT_AFTER_LOAD_MS = 8_000
```

### Colonnes attendues

Les colonnes doivent être maintenues dans la variable suivante :

```python
EXPECTED_COLUMNS = [
    "Booking ID",
    "Date",
    "Space IDs",
    "Space Names",
    "Start Date",
    "End Date",
    "Creator ID",
    "Creator First Name",
    "Creator Last Name",
    "Creator Email",
    "Occurrence Count",
    "Cancelled",
    "Cancelled Date",
]
```

Si une colonne est ajoutée ou renommée dans Zapier, cette liste pourrait devoir être ajustée.

---

## Sécurité

Pour protéger l’accès aux données :

- ne pas inscrire l’URL Zapier directement dans `main.py`;
- ne pas publier l’URL Zapier dans le README;
- conserver l’URL dans le secret `ZAPIER_TABLE_URL`;
- limiter les personnes ayant accès aux paramètres du dépôt;
- éviter d’ajouter les fichiers de débogage contenant des réponses JSON au dépôt;
- vérifier si le CSV contient des renseignements personnels avant de rendre le dépôt public.

Puisque le fichier contient notamment des noms et des adresses courriel, le dépôt devrait demeurer privé si ces colonnes sont conservées.

---

## Fichier de débogage

Le script définit également le chemin suivant :

```python
DEBUG_FILE = SCRIPT_FOLDER / "zapier_debug.json"
```

Dans la version actuelle, ce fichier n’est pas écrit automatiquement.

Il peut être utilisé ultérieurement pour enregistrer les réponses JSON capturées lors d’une analyse technique. Un tel fichier pourrait contenir des renseignements sensibles et ne devrait pas être publié dans le dépôt.

Il est recommandé de l’ajouter au fichier `.gitignore` :

```gitignore
zapier_debug.json
.venv/
__pycache__/
*.pyc
```

---

## Limites conn*es

L’extraction dépend de la stru*ture actuelle de l’application Zap*er Tables.

Des ajustements pourra*ent être nécessaires si Zapier mod*fie :

- les adresses des appels r*seau;
- le format des réponses JSO*;
- la structure des champs;
- la *éthode de chargement des enregistr*ments;
- le comportement de défile*ent de la table.

L’extraction dép*nd également du chargement complet*des données pendant la session Chr*mium.

---

## Résultat attendu

A*rès une exécution réussie, le dépô* contient une version à jour du fi*hier :

```text
Presence_Skedda.cs*
```

Si le contenu diffère de la *ersion précédente, GitHub Actions *rée automatiquement une nouvelle p*blication dans l’historique Git.

*i le contenu est identique, aucune*publication inutile n’est créée.

*--

## Maintenance

Lorsqu’une modification est apportée à la table Zapier, vérifier les éléments suivants :

- les noms des colonnes;
- la*présence de `Booking ID`;
- le for*at des dates;
- les règles de dédo*blonnage;
- le nombre de lignes ex*ortées;
- les journaux GitHub Acti*ns;
- les permissions d’écriture d* workflow;
- la validité du secret*`ZAPIER_TABLE_URL`.

