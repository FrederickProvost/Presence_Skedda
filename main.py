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

# Dans GitHub Actions, l'URL sera fournie par GitHub Secrets
ZAPIER_URL = os.environ.get("ZAPIER_TABLE_URL")

SCRIPT_FOLDER = Path(__file__).resolve().parent

OUTPUT_FILE = SCRIPT_FOLDER / "Presence_Skedda.csv"
DEBUG_FILE = SCRIPT_FOLDER / "zapier_debug.json"

# IMPORTANT pour GitHub Actions :
# Chromium doit fonctionner sans interface graphique
HEADLESS = True

PAGE_TIMEOUT_MS = 120_000
WAIT_AFTER_LOAD_MS = 8_000


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

                    simple_values.append(
                        str(possible_value)
                    )

                else:

                    simple_values.append(
                        json.dumps(
                            item,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )

            else:

                simple_values.append(
                    str(item)
                )

        return ", ".join(simple_values)

    if isinstance(value, dict):

        possible_value = (
            value.get("value")
            or value.get("name")
            or value.get("label")
            or value.get("text")
        )

        if possible_value is not None:
            return serialize_value(
                possible_value
            )

        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    return str(value)


def extract_last_key(source_key):

    source_key = str(
        source_key
    ).strip()

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
            inspect_field_definitions(
                item
            )

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

        possible_name = str(
            possible_name
        ).strip()

        expected_lookup = {
            normalize_key(column): column
            for column in EXPECTED_COLUMNS
        }

        normalized_name = normalize_key(
            possible_name
        )

        if normalized_name in expected_lookup:

            official_name = expected_lookup[
                normalized_name
            ]

            field_id = str(
                possible_id
            ).strip()

            field_map[field_id] = (
                official_name
            )

            field_map[
                f"f{field_id}"
            ] = official_name

    for value in obj.values():

        inspect_field_definitions(
            value
        )


# ============================================================
# CORRESPONDANCE CHAMPS
# ============================================================

def get_column_name(source_key):

    source_key = str(
        source_key
    ).strip()

    candidates = [
        source_key,
        extract_last_key(
            source_key
        ),
    ]

    for candidate in candidates:

        if candidate in field_map:
            return field_map[
                candidate
            ]

        if candidate.startswith("f"):

            without_f = candidate[1:]

            if without_f in field_map:

                return field_map[
                    without_f
                ]

    normalized_source = (
        normalize_key(
            source_key
        )
    )

    for column in EXPECTED_COLUMNS:

        normalized_column = (
            normalize_key(
                column
            )
        )

        if (
            normalized_source
            == normalized_column
        ):
            return column

        if normalized_source.endswith(
            normalized_column
        ):
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

    flattened = flatten_dict(
        obj
    )

    for source_key, value in flattened.items():

        column = get_column_name(
            source_key
        )

        if column is not None:

            row[column] = (
                serialize_value(
                    value
                )
            )

            matched_columns.add(
                column
            )

    for possible_container in [
        "cells",
        "values",
        "fields",
        "data",
    ]:

        container = obj.get(
            possible_container
        )

        if not isinstance(
            container,
            list
        ):
            continue

        for cell in container:

            if not isinstance(
                cell,
                dict
            ):
                continue

            cell_field_id = (
                cell.get("field_id")
                or cell.get("fieldId")
                or cell.get("field")
                or cell.get("key")
                or cell.get("id")
            )

            if "value" in cell:

                cell_value = (
                    cell.get("value")
                )

            else:

                cell_value = (
                    cell.get("data")
                )

            if cell_field_id is None:
                continue

            column = get_column_name(
                cell_field_id
            )

            if column is not None:

                row[column] = (
                    serialize_value(
                        cell_value
                    )
                )

                matched_columns.add(
                    column
                )

    score = len(
        matched_columns
    )

    return row, score


# ============================================================
# RECHERCHE RÉCURSIVE
# ============================================================

def inspect_for_records(
    obj,
    path="root",
):

    if isinstance(obj, list):

        for index, item in enumerate(
            obj
        ):

            inspect_for_records(
                item,
                f"{path}[{index}]",
            )

        return

    if not isinstance(obj, dict):
        return

    row, score = (
        convert_object_to_row(
            obj
        )
    )

    if score >= 3:

        extracted_records.append(
            {
                "path": path,
                "score": score,
                "row": row,
            }
        )

    for key, value in obj.items():

        if isinstance(
            value,
            (dict, list)
        ):

            inspect_for_records(
                value,
                f"{path}.{key}",
            )


# ============================================================
# CAPTURE RÉSEAU
# ============================================================

def capture_response(response):

    try:

        response_url = (
            response.url
        )

        content_type = (
            response.headers.get(
                "content-type",
                "",
            ).lower()
        )

        if "json" not in content_type:
            return

        if (
            "tables.zapier.com"
            not in response_url
        ):
            return

        data = response.json()

        captured_json.append(
            {
                "url": response_url,
                "status": response.status,
                "data": data,
            }
        )

        if "/fields" in response_url:

            print(
                "Définitions des champs reçues."
            )

            inspect_field_definitions(
                data
            )

        elif (
            "/records/query"
            in response_url
        ):

            print(
                "Enregistrements reçus."
            )

    except Exception as error:

        print(
            f"Erreur capture : {error}"
        )


# ============================================================
# DÉDOUBLONNAGE
# ============================================================

def deduplicate_records(candidates):
    best_by_key = {}

    for index, candidate in enumerate(candidates):
        row = candidate["row"]
        score = candidate["score"]

        booking_id = (
            row.get(
                "Booking ID",
                "",
            ).strip()
        )

        # ----------------------------------------------------
        # CAS 1 : Booking ID commence par "Ex"
        # On conserve TOUTES les lignes
        # ----------------------------------------------------
        if booking_id.lower().startswith("ex"):
            unique_key = (
                "booking_id_ex",
                booking_id,
                index,
            )

        # ----------------------------------------------------
        # CAS 2 : Booking ID normal
        # Même logique qu'avant :
        # une seule ligne par Booking ID
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
            unique_key = tuple(
                row.get(
                    column,
                    "",
                )
                for column
                in EXPECTED_COLUMNS
            )

        existing = best_by_key.get(
            unique_key
        )

        if existing is None:
            best_by_key[
                unique_key
            ] = candidate

        elif score > existing["score"]:
            best_by_key[
                unique_key
            ] = candidate

    return [
        candidate["row"]
        for candidate
        in best_by_key.values()
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

        writer.writerows(
            records
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
    # Validation du GitHub Secret
    # --------------------------------------------------------

    if not ZAPIER_URL:

        print(
            "ERREUR : GitHub Secret "
            "'ZAPIER_TABLE_URL' absent."
        )

        sys.exit(1)

    print(
        "GitHub Secret chargé."
    )

    print(
        f"Table ID : {TABLE_ID}"
    )

    # --------------------------------------------------------
    # Chromium
    # --------------------------------------------------------

    with sync_playwright() as p:

        browser = (
            p.chromium.launch(
                headless=HEADLESS
            )
        )

        context = (
            browser.new_context(
                viewport={
                    "width": 1920,
                    "height": 1080,
                },
                locale="fr-CA",
            )
        )

        page = (
            context.new_page()
        )

        page.on(
            "response",
            capture_response,
        )

        print(
            "Ouverture Zapier..."
        )

        page.goto(
            ZAPIER_URL,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT_MS,
        )

        print(
            "Page chargée."
        )

        page.wait_for_timeout(
            WAIT_AFTER_LOAD_MS
        )

        # ----------------------------------------------------
        # Forcer le chargement des contenus scrollables
        # ----------------------------------------------------

        print(
            "Chargement des lignes..."
        )

        for _ in range(30):

            page.evaluate(
                """
                () => {

                    const elements =
                        document.querySelectorAll("*");

                    for (
                        const element
                        of elements
                    ) {

                        if (
                            element.scrollHeight >
                            element.clientHeight
                        ) {

                            element.scrollTop =
                                element.scrollHeight;
                        }
                    }
                }
                """
            )

            page.wait_for_timeout(
                300
            )

        page.wait_for_timeout(
            3000
        )

        browser.close()

    # --------------------------------------------------------
    # Analyse des réponses
    # --------------------------------------------------------

    print("")
    print(
        f"Réponses Zapier : "
        f"{len(captured_json)}"
    )

    print(
        f"Champs reconnus : "
        f"{len({
            value
            for value
            in field_map.values()
        })}"
    )

    for captured in captured_json:

        if (
            "/records/query"
            in captured["url"]
        ):

            inspect_for_records(
                captured["data"],
                path="records_query",
            )

    # --------------------------------------------------------
    # Nettoyage
    # --------------------------------------------------------

    records = (
        deduplicate_records(
            extracted_records
        )
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
            "ERREUR : "
            "aucune ligne trouvée."
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

    write_csv(
        records
    )

    # --------------------------------------------------------
    # Résultat
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("EXPORT TERMINÉ")
    print("=" * 60)

    print(
        f"Lignes : {len(records)}"
    )

    print(
        f"Colonnes : "
        f"{len(EXPECTED_COLUMNS)}"
    )

    print(
        f"CSV : {OUTPUT_FILE}"
    )

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
