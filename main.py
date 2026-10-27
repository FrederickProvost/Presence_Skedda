from playwright.sync_api import sync_playwright
from pathlib import Path
from datetime import datetime
import csv
import json
import os
import re
import sys


# ============================================================
# CONFIGURATION
# ============================================================

TABLE_ID = "01M4XMP5Q9SG9RP6X9BY8A8SHA"

# Dans GitHub Actions, l'URL est fournie par GitHub Secrets
ZAPIER_URL = os.environ.get("ZAPIER_TABLE_URL")

SCRIPT_FOLDER = Path(__file__).resolve().parent

OUTPUT_FILE = SCRIPT_FOLDER / "Presence_Skedda.csv"
DEBUG_FILE = SCRIPT_FOLDER / "zapier_debug.json"

HEADLESS = True

PAGE_TIMEOUT_MS = 120_000
WAIT_AFTER_LOAD_MS = 8_000
WAIT_AFTER_PAGE_CHANGE_MS = 3_000

MAX_PAGES_SAFETY = 500


# ============================================================
# COLONNES
# ============================================================

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


# ============================================================
# VARIABLES
# ============================================================

captured_json = []
field_map = {}
extracted_records = []

capture_enabled = True


# ============================================================
# OUTILS
# ============================================================

def normalize_key(value):
    if value is None:
        return ""

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).strip().lower(),
    )


def serialize_value(value):
    if value is None:
        return ""

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, list):
        simple_values = []

        for item in value:
            if isinstance(item, dict):
                possible_value = (
                    item.get("value")
                    or item.get("name")
                    or item.get("label")
                    or item.get("text")
                    or item.get("id")
                )

                if possible_value is not None:
                    simple_values.append(str(possible_value))
                else:
                    simple_values.append(
                        json.dumps(
                            item,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
            else:
                simple_values.append(str(item))

        return ", ".join(simple_values)

    if isinstance(value, dict):
        possible_value = (
            value.get("value")
            or value.get("name")
            or value.get("label")
            or value.get("text")
        )

        if possible_value is not None:
            return serialize_value(possible_value)

        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    return str(value)


def extract_last_key(source_key):
    source_key = str(source_key).strip()

    parts = re.split(
        r"[.\[\]/]",
        source_key,
    )

    parts = [
        part
        for part in parts
        if part
    ]

    if not parts:
        return source_key

    return parts[-1]


def flatten_dict(source, parent_key=""):
    output = {}

    if not isinstance(source, dict):
        return output

    for key, value in source.items():
        full_key = (
            f"{parent_key}.{key}"
            if parent_key
            else str(key)
        )

        if isinstance(value, dict):
            output.update(
                flatten_dict(
                    value,
                    full_key,
                )
            )
        else:
            output[full_key] = value

    return output


# ============================================================
# CHAMPS
# ============================================================

def inspect_field_definitions(obj):
    if isinstance(obj, list):
        for item in obj:
            inspect_field_definitions(item)
        return

    if not isinstance(obj, dict):
        return

    possible_id = (
        obj.get("id")
        or obj.get("field_id")
        or obj.get("fieldId")
        or obj.get("key")
    )

    possible_name = (
        obj.get("name")
        or obj.get("label")
        or obj.get("title")
        or obj.get("field_name")
        or obj.get("fieldName")
    )

    if (
        possible_id is not None
        and possible_name is not None
    ):
        possible_name = str(possible_name).strip()

        expected_lookup = {
            normalize_key(column): column
            for column in EXPECTED_COLUMNS
        }

        normalized_name = normalize_key(possible_name)

        if normalized_name in expected_lookup:
            official_name = expected_lookup[normalized_name]
            field_id = str(possible_id).strip()

            field_map[field_id] = official_name
            field_map[f"f{field_id}"] = official_name

    for value in obj.values():
        inspect_field_definitions(value)


# ============================================================
# CORRESPONDANCE CHAMPS
# ============================================================

def get_column_name(source_key):
    source_key = str(source_key).strip()

    candidates = [
        source_key,
        extract_last_key(source_key),
    ]

    for candidate in candidates:
        if candidate in field_map:
            return field_map[candidate]

        if candidate.startswith("f"):
            without_f = candidate[1:]

            if without_f in field_map:
                return field_map[without_f]

    normalized_source = normalize_key(source_key)

    for column in EXPECTED_COLUMNS:
        normalized_column = normalize_key(column)

        if normalized_source == normalized_column:
            return column

        if normalized_source.endswith(normalized_column):
            return column

    return None


# ============================================================
# CONVERSION DES ENREGISTREMENTS
# ============================================================

def convert_object_to_row(obj):
    if not isinstance(obj, dict):
        return None, 0

    row = {
        column: ""
        for column in EXPECTED_COLUMNS
    }

    matched_columns = set()

    flattened = flatten_dict(obj)

    for source_key, value in flattened.items():
        column = get_column_name(source_key)

        if column is not None:
            row[column] = serialize_value(value)
            matched_columns.add(column)

    for possible_container in [
        "cells",
        "values",
        "fields",
        "data",
    ]:
        container = obj.get(possible_container)

        if not isinstance(container, list):
            continue

        for cell in container:
            if not isinstance(cell, dict):
                continue

            cell_field_id = (
                cell.get("field_id")
                or cell.get("fieldId")
                or cell.get("field")
                or cell.get("key")
                or cell.get("id")
            )

            if "value" in cell:
                cell_value = cell.get("value")
            else:
                cell_value = cell.get("data")

            if cell_field_id is None:
                continue

            column = get_column_name(cell_field_id)

            if column is not None:
                row[column] = serialize_value(cell_value)
                matched_columns.add(column)

    score = len(matched_columns)

    return row, score


# ============================================================
# RECHERCHE RÉCURSIVE
# ============================================================

def inspect_for_records(obj, path="root"):
    if isinstance(obj, list):
        for index, item in enumerate(obj):
            inspect_for_records(
                item,
                f"{path}[{index}]",
            )
        return

    if not isinstance(obj, dict):
        return

    row, score = convert_object_to_row(obj)

    if score >= 3:
        extracted_records.append(
            {
                "path": path,
                "score": score,
                "row": row,
            }
        )

    for key, value in obj.items():
        if isinstance(value, (dict, list)):
            inspect_for_records(
                value,
                f"{path}.{key}",
            )


# ============================================================
# CAPTURE RÉSEAU
# ============================================================

def capture_response(response):
    global capture_enabled

    try:
        response_url = response.url

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if "json" not in content_type:
            return

        if "tables.zapier.com" not in response_url:
            return

        data = response.json()

        # Les définitions de champs sont toujours utiles
        if "/fields" in response_url:
            inspect_field_definitions(data)

            print("Définitions des champs reçues.")

            return

        # On ignore les réponses d'enregistrements pendant
        # la navigation initiale vers la première page.
        if (
            "/records/query" in response_url
            and not capture_enabled
        ):
            return

        captured_json.append(
            {
                "url": response_url,
                "status": response.status,
                "data": data,
            }
        )

        if "/records/query" in response_url:
            print("Enregistrements reçus.")

    except Exception as error:
        print(f"Erreur capture : {error}")


# ============================================================
# PAGINATION
# ============================================================

def get_pagination_status(page):
    """
    Recherche un texte comme :
        1 of 2
        2 of 2

    Retourne :
        current_page, total_pages

    Si aucune pagination n'est visible :
        1, 1
    """

    result = page.evaluate(
        """
        () => {
            const elements = Array.from(
                document.querySelectorAll("body *")
            );

            for (const element of elements) {
                const text = (
                    element.innerText || ""
                ).trim();

                const match = text.match(
                    /^(\\d+)\\s+of\\s+(\\d+)$/
                );

                if (match) {
                    return {
                        current: Number(match[1]),
                        total: Number(match[2])
                    };
                }
            }

            return {
                current: 1,
                total: 1
            };
        }
        """
    )

    current_page = int(result.get("current", 1))
    total_pages = int(result.get("total", 1))

    return current_page, total_pages


def click_pagination_button(page, direction):
    """
    direction :
        first
        previous
        next
        last
    """

    clicked = page.evaluate(
        """
        (direction) => {
            function isClickable(element) {
                if (!element) {
                    return false;
                }

                const tag = element.tagName.toLowerCase();

                return (
                    tag === "button"
                    || tag === "a"
                    || element.getAttribute("role") === "button"
                );
            }

            function isDisabled(element) {
                if (!element) {
                    return true;
                }

                return (
                    element.disabled === true
                    || element.getAttribute("disabled") !== null
                    || element.getAttribute("aria-disabled") === "true"
                );
            }

            function getLabel(element) {
                return [
                    element.getAttribute("aria-label"),
                    element.getAttribute("title"),
                    element.innerText,
                    element.textContent
                ]
                    .filter(Boolean)
                    .join(" ")
                    .trim()
                    .toLowerCase();
            }

            const labelPatterns = {
                first: [
                    "first page",
                    "go to first",
                    "première page",
                    "premiere page"
                ],
                previous: [
                    "previous page",
                    "go to previous",
                    "page précédente",
                    "page precedente"
                ],
                next: [
                    "next page",
                    "go to next",
                    "page suivante"
                ],
                last: [
                    "last page",
                    "go to last",
                    "dernière page",
                    "derniere page"
                ]
            };

            const clickableElements = Array.from(
                document.querySelectorAll(
                    'button, a, [role="button"]'
                )
            );

            for (const element of clickableElements) {
                const label = getLabel(element);

                const matches = labelPatterns[
                    direction
                ].some(
                    pattern => label.includes(pattern)
                );

                if (
                    matches
                    && !isDisabled(element)
                ) {
                    element.click();
                    return true;
                }
            }

            /*
            Fallback pour l'interface Zapier visible dans
            la capture d'écran :

            [première] [précédente]  1 of 2  [suivante] [dernière]
            */

            const allElements = Array.from(
                document.querySelectorAll("body *")
            );

            let statusElement = null;

            for (const element of allElements) {
                const text = (
                    element.innerText || ""
                ).trim();

                if (/^\\d+\\s+of\\s+\\d+$/.test(text)) {
                    statusElement = element;
                    break;
                }
            }

            if (!statusElement) {
                return false;
            }

            let container = statusElement.parentElement;

            for (let level = 0; level < 6; level++) {
                if (!container) {
                    break;
                }

                const buttons = Array.from(
                    container.querySelectorAll(
                        'button, a, [role="button"]'
                    )
                ).filter(isClickable);

                if (buttons.length >= 4) {
                    let target = null;

                    if (direction === "first") {
                        target = buttons[0];
                    } else if (direction === "previous") {
                        target = buttons[1];
                    } else if (direction === "next") {
                        target = buttons[
                            buttons.length - 2
                        ];
                    } else if (direction === "last") {
                        target = buttons[
                            buttons.length - 1
                        ];
                    }

                    if (
                        target
                        && !isDisabled(target)
                    ) {
                        target.click();
                        return true;
                    }

                    return false;
                }

                container = container.parentElement;
            }

            return false;
        }
        """,
        direction,
    )

    return bool(clicked)


def wait_for_page_number(
    page,
    expected_page,
    timeout_ms=30_000,
):
    page.wait_for_function(
        """
        expectedPage => {
            const elements = Array.from(
                document.querySelectorAll("body *")
            );

            return elements.some(element => {
                const text = (
                    element.innerText || ""
                ).trim();

                const match = text.match(
                    /^(\\d+)\\s+of\\s+(\\d+)$/
                );

                return (
                    match
                    && Number(match[1]) === expectedPage
                );
            });
        }
        """,
        arg=expected_page,
        timeout=timeout_ms,
    )


def scroll_current_page(page):
    """
    Force le chargement des lignes de la page actuelle.
    """

    previous_state = None
    stable_iterations = 0

    for _ in range(40):
        state = page.evaluate(
            """
            () => {
                let changed = false;
                let largestScrollHeight = 0;
                let largestScrollTop = 0;

                const elements = document.querySelectorAll("*");

                for (const element of elements) {
                    if (
                        element.scrollHeight >
                        element.clientHeight + 5
                    ) {
                        largestScrollHeight = Math.max(
                            largestScrollHeight,
                            element.scrollHeight
                        );

                        element.scrollTop =
                            element.scrollHeight;

                        largestScrollTop = Math.max(
                            largestScrollTop,
                            element.scrollTop
                        );

                        changed = true;
                    }
                }

                window.scrollTo(
                    0,
                    document.body.scrollHeight
                );

                return {
                    changed,
                    largestScrollHeight,
                    largestScrollTop,
                    bodyHeight:
                        document.body.scrollHeight
                };
            }
            """
        )

        state_key = (
            state.get("largestScrollHeight"),
            state.get("largestScrollTop"),
            state.get("bodyHeight"),
        )

        if state_key == previous_state:
            stable_iterations += 1
        else:
            stable_iterations = 0

        previous_state = state_key

        page.wait_for_timeout(300)

        if stable_iterations >= 4:
            break

    page.wait_for_timeout(WAIT_AFTER_PAGE_CHANGE_MS)


def go_to_first_page(page):
    current_page, total_pages = get_pagination_status(page)

    print(
        f"Page affichée au départ : "
        f"{current_page} sur {total_pages}"
    )

    if current_page == 1:
        return total_pages

    print("Retour à la première page...")

    clicked = click_pagination_button(
        page,
        "first",
    )

    if clicked:
        wait_for_page_number(
            page,
            1,
        )

        page.wait_for_timeout(
            WAIT_AFTER_PAGE_CHANGE_MS
        )

        return total_pages

    # Si le bouton Première page n'est pas détecté,
    # on clique plusieurs fois sur Précédente.

    while current_page > 1:
        clicked = click_pagination_button(
            page,
            "previous",
        )

        if not clicked:
            raise RuntimeError(
                "Impossible de revenir à la "
                "première page Zapier."
            )

        expected_page = current_page - 1

        wait_for_page_number(
            page,
            expected_page,
        )

        page.wait_for_timeout(
            WAIT_AFTER_PAGE_CHANGE_MS
        )

        current_page, total_pages = (
            get_pagination_status(page)
        )

    return total_pages


def capture_all_pages(page):
    global capture_enabled

    # Désactive temporairement la capture pendant
    # le retour vers la première page.
    capture_enabled = False

    total_pages = go_to_first_page(page)

    if total_pages > MAX_PAGES_SAFETY:
        raise RuntimeError(
            f"Nombre de pages anormal : {total_pages}"
        )

    # Efface les réponses capturées pendant
    # le chargement initial.
    captured_json.clear()
    extracted_records.clear()

    capture_enabled = True

    print("")
    print(
        f"Nombre total de pages détecté : "
        f"{total_pages}"
    )

    for expected_page in range(
        1,
        total_pages + 1,
    ):
        current_page, detected_total = (
            get_pagination_status(page)
        )

        print("")
        print(
            f"Capture de la page "
            f"{current_page} sur {detected_total}..."
        )

        # Pour la première page, les données peuvent déjà
        # être chargées. On recharge donc la page 1 pour
        # provoquer une nouvelle réponse /records/query.
        if expected_page == 1:
            before_count = len(captured_json)

            page.reload(
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )

            page.wait_for_timeout(
                WAIT_AFTER_LOAD_MS
            )

            current_page, total_after_reload = (
                get_pagination_status(page)
            )

            # Zapier pourrait restaurer l'ancienne page.
            if current_page != 1:
                capture_enabled = False

                go_to_first_page(page)

                captured_json.clear()
                capture_enabled = True

                # Clique sur suivante puis précédente afin
                # de forcer une requête fraîche de page 1,
                # seulement si plusieurs pages existent.
                if total_after_reload > 1:
                    clicked = click_pagination_button(
                        page,
                        "next",
                    )

                    if clicked:
                        wait_for_page_number(
                            page,
                            2,
                        )

                        page.wait_for_timeout(
                            WAIT_AFTER_PAGE_CHANGE_MS
                        )

                        capture_enabled = False

                        click_pagination_button(
                            page,
                            "previous",
                        )

                        wait_for_page_number(
                            page,
                            1,
                        )

                        captured_json.clear()
                        capture_enabled = True

                        page.reload(
                            wait_until="domcontentloaded",
                            timeout=PAGE_TIMEOUT_MS,
                        )

                        page.wait_for_timeout(
                            WAIT_AFTER_LOAD_MS
                        )

                        current_page, _ = (
                            get_pagination_status(page)
                        )

                        if current_page != 1:
                            capture_enabled = False
                            go_to_first_page(page)
                            captured_json.clear()
                            capture_enabled = True

            scroll_current_page(page)

            after_count = len(captured_json)

            print(
                "Réponses capturées sur la page 1 : "
                f"{after_count - before_count}"
            )

        else:
            previous_response_count = len(captured_json)

            clicked = click_pagination_button(
                page,
                "next",
            )

            if not clicked:
                raise RuntimeError(
                    "Le bouton Page suivante n'a "
                    f"pas été détecté pour accéder "
                    f"à la page {expected_page}."
                )

            wait_for_page_number(
                page,
                expected_page,
            )

            # Attend qu'une nouvelle réponse réseau arrive.
            try:
                page.wait_for_function(
                    """
                    () => true
                    """,
                    timeout=500,
                )
            except Exception:
                pass

            page.wait_for_timeout(
                WAIT_AFTER_PAGE_CHANGE_MS
            )

            scroll_current_page(page)

            new_response_count = (
                len(captured_json)
                - previous_response_count
            )

            print(
                "Nouvelles réponses capturées : "
                f"{new_response_count}"
            )

    capture_enabled = False

    print("")
    print(
        "Toutes les pages Zapier ont été visitées."
    )


# ============================================================
# DÉDOUBLONNAGE
# ============================================================

def deduplicate_records(candidates):
    best_by_key = {}

    for index, candidate in enumerate(candidates):
        row = candidate["row"]
        score = candidate["score"]

        booking_id = row.get(
            "Booking ID",
            "",
        ).strip()

        # ----------------------------------------------------
        # CAS 1 : Booking ID commence par Ex
        #
        # On garde toutes les occurrences ayant des données
        # différentes. Une même réponse réseau capturée deux
        # fois ne créera pas de doublon CSV.
        # ----------------------------------------------------

        if booking_id.lower().startswith("ex"):
            unique_key = (
                "booking_id_ex",
                booking_id,
                tuple(
                    row.get(column, "")
                    for column in EXPECTED_COLUMNS
                ),
            )

        # ----------------------------------------------------
        # CAS 2 : Booking ID normal
        #
        # Une seule ligne par Booking ID.
        # ----------------------------------------------------

        elif booking_id:
            unique_key = (
                "booking_id",
                booking_id,
            )

        # ----------------------------------------------------
        # CAS 3 : Aucun Booking ID
        # ----------------------------------------------------

        else:
            unique_key = (
                "no_booking_id",
                tuple(
                    row.get(column, "")
                    for column in EXPECTED_COLUMNS
                ),
            )

        existing = best_by_key.get(unique_key)

        if existing is None:
            best_by_key[unique_key] = candidate

        elif score > existing["score"]:
            best_by_key[unique_key] = candidate

    return [
        candidate["row"]
        for candidate in best_by_key.values()
    ]


# ============================================================
# EXPORT CSV
# ============================================================

def write_csv(records):
    with OUTPUT_FILE.open(
        mode="w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=EXPECTED_COLUMNS,
            delimiter=",",
            quoting=csv.QUOTE_MINIMAL,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(records)


def write_debug_file():
    debug_content = {
        "table_id": TABLE_ID,
        "captured_response_count": len(captured_json),
        "recognized_fields": sorted(
            set(field_map.values())
        ),
        "candidate_count": len(extracted_records),
        "responses": captured_json,
    }

    with DEBUG_FILE.open(
        mode="w",
        encoding="utf-8",
    ) as debug_file:
        json.dump(
            debug_content,
            debug_file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# MAIN
# ============================================================

def main():
    print("")
    print("=" * 60)
    print("EXPORT ZAPIER TABLE")
    print("=" * 60)
    print("")

    # --------------------------------------------------------
    # Validation GitHub Secret
    # --------------------------------------------------------

    if not ZAPIER_URL:
        print(
            "ERREUR : GitHub Secret "
            "'ZAPIER_TABLE_URL' absent."
        )

        sys.exit(1)

    print("GitHub Secret chargé.")
    print(f"Table ID : {TABLE_ID}")

    # --------------------------------------------------------
    # Chromium
    # --------------------------------------------------------

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=HEADLESS
            )

            context = browser.new_context(
                viewport={
                    "width": 1920,
                    "height": 1080,
                },
                locale="fr-CA",
            )

            page = context.new_page()

            page.on(
                "response",
                capture_response,
            )

            print("Ouverture Zapier...")

            page.goto(
                ZAPIER_URL,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )

            print("Page chargée.")

            page.wait_for_timeout(
                WAIT_AFTER_LOAD_MS
            )

            capture_all_pages(page)

            browser.close()

    except Exception as error:
        print("")
        print(
            "ERREUR pendant la navigation Zapier :"
        )
        print(str(error))

        try:
            write_debug_file()
            print(f"Debug : {DEBUG_FILE}")
        except Exception:
            pass

        sys.exit(1)

    # --------------------------------------------------------
    # Analyse des réponses
    # --------------------------------------------------------

    print("")
    print(
        f"Réponses Zapier capturées : "
        f"{len(captured_json)}"
    )

    recognized_fields = {
        value
        for value in field_map.values()
    }

    print(
        f"Champs reconnus : "
        f"{len(recognized_fields)}"
    )

    for captured_index, captured in enumerate(
        captured_json
    ):
        if "/records/query" in captured["url"]:
            inspect_for_records(
                captured["data"],
                path=(
                    "records_query"
                    f"[{captured_index}]"
                ),
            )

    print(
        f"Candidats détectés : "
        f"{len(extracted_records)}"
    )

    # --------------------------------------------------------
    # Nettoyage
    # --------------------------------------------------------

    records = deduplicate_records(
        extracted_records
    )

    records = [
        row
        for row in records
        if row.get(
            "Booking ID",
            "",
        ).strip()
    ]

    if not records:
        print(
            "ERREUR : aucune ligne trouvée."
        )

        write_debug_file()

        print(
            f"Fichier debug créé : "
            f"{DEBUG_FILE}"
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Tri
    # --------------------------------------------------------

    records.sort(
        key=lambda row: (
            row.get(
                "Start Date",
                "",
            ),
            row.get(
                "Booking ID",
                "",
            ),
        )
    )

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    write_csv(records)
    write_debug_file()

    # --------------------------------------------------------
    # Résultat
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("EXPORT TERMINÉ")
    print("=" * 60)

    print(f"Lignes : {len(records)}")

    print(
        f"Colonnes : "
        f"{len(EXPECTED_COLUMNS)}"
    )

    print(f"CSV : {OUTPUT_FILE}")
    print(f"Debug : {DEBUG_FILE}")

    print(
        "Exécution : "
        + datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )


# ============================================================
# DÉMARRAGE
# ============================================================

if __name__ == "__main__":
    main()
