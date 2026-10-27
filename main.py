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
SCREENSHOT_FILE = SCRIPT_FOLDER / "zapier_pagination_error.png"

HEADLESS = True

PAGE_TIMEOUT_MS = 120_000
WAIT_AFTER_LOAD_MS = 8_000
WAIT_AFTER_PAGE_CHANGE_MS = 3_000

# Protection contre une boucle infinie
MAX_PAGES = 500


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
# DÉFINITIONS DES CHAMPS
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

            field_map[field_id] = official_name

            field_map[
                f"f{field_id}"
            ] = official_name

    for value in obj.values():

        inspect_field_definitions(
            value
        )


# ============================================================
# CORRESPONDANCE DES CHAMPS
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

    normalized_source = normalize_key(
        source_key
    )

    for column in EXPECTED_COLUMNS:

        normalized_column = normalize_key(
            column
        )

        if normalized_source == normalized_column:
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

            row[column] = serialize_value(
                value
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

                cell_value = cell.get(
                    "value"
                )

            else:

                cell_value = cell.get(
                    "data"
                )

            if cell_field_id is None:
                continue

            column = get_column_name(
                cell_field_id
            )

            if column is not None:

                row[column] = serialize_value(
                    cell_value
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

    row, score = convert_object_to_row(
        obj
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
            (dict, list),
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

        elif "/records/query" in response_url:

            print(
                "Enregistrements reçus."
            )

    except Exception as error:

        print(
            f"Erreur capture : {error}"
        )


def count_records_query_responses():

    return sum(
        1
        for captured in captured_json
        if "/records/query" in captured["url"]
    )


# ============================================================
# PAGINATION
# ============================================================

def get_pagination_status(page):
    """
    Recherche un texte visible comme :

        Page 1 of 2
        Page 2 of 2

    Si le panneau de pagination est fermé :
        None, None
    """

    result = page.evaluate(
        """
        () => {
            function isVisible(element) {
                const rect =
                    element.getBoundingClientRect();

                const style =
                    window.getComputedStyle(element);

                return (
                    rect.width > 0 &&
                    rect.height > 0 &&
                    style.display !== "none" &&
                    style.visibility !== "hidden"
                );
            }

            const elements = Array.from(
                document.querySelectorAll("*")
            );

            for (const element of elements) {
                if (!isVisible(element)) {
                    continue;
                }

                const text = (
                    element.innerText || ""
                ).trim();

                const match = text.match(
                    /^Page\\s+(\\d+)\\s+of\\s+(\\d+)$/i
                );

                if (match) {
                    return {
                        current: Number(match[1]),
                        total: Number(match[2])
                    };
                }
            }

            return {
                current: null,
                total: null
            };
        }
        """
    )

    current_page = result.get(
        "current"
    )

    total_pages = result.get(
        "total"
    )

    if (
        current_page is None
        or total_pages is None
    ):
        return None, None

    return (
        int(current_page),
        int(total_pages),
    )


def pagination_panel_is_open(page):

    current_page, total_pages = (
        get_pagination_status(
            page
        )
    )

    return (
        current_page is not None
        and total_pages is not None
    )


def scroll_current_page(page):
    """
    Descend tous les conteneurs défilables afin que Zapier
    charge les lignes de la page actuelle.
    """

    print(
        "Chargement complet des lignes..."
    )

    previous_state = None
    stable_iterations = 0

    for _ in range(50):

        state = page.evaluate(
            """
            () => {
                let maximumScrollHeight = 0;
                let maximumScrollTop = 0;

                const elements =
                    document.querySelectorAll("*");

                for (const element of elements) {
                    if (
                        element.scrollHeight >
                        element.clientHeight + 5
                    ) {
                        element.scrollTop =
                            element.scrollHeight;

                        maximumScrollHeight =
                            Math.max(
                                maximumScrollHeight,
                                element.scrollHeight
                            );

                        maximumScrollTop =
                            Math.max(
                                maximumScrollTop,
                                element.scrollTop
                            );
                    }
                }

                window.scrollTo(
                    0,
                    document.body.scrollHeight
                );

                return {
                    maximumScrollHeight,
                    maximumScrollTop,
                    bodyHeight:
                        document.body.scrollHeight
                };
            }
            """
        )

        state_key = (
            state.get(
                "maximumScrollHeight"
            ),
            state.get(
                "maximumScrollTop"
            ),
            state.get(
                "bodyHeight"
            ),
        )

        if state_key == previous_state:
            stable_iterations += 1
        else:
            stable_iterations = 0

        previous_state = state_key

        page.wait_for_timeout(
            300
        )

        if stable_iterations >= 5:
            break

    page.wait_for_timeout(
        2_000
    )


def open_pagination_panel(page):
    """
    Clique sur le contrôle situé immédiatement
    à gauche du compteur de records.

    Exemple :

        [contrôle d'ouverture] [1,017 records]
    """

    if pagination_panel_is_open(
        page
    ):

        print(
            "Le panneau de pagination est déjà ouvert."
        )

        return True

    print(
        "Ouverture du panneau de pagination..."
    )

    result = page.evaluate(
        """
        () => {
            function isVisible(element) {
                const rect =
                    element.getBoundingClientRect();

                const style =
                    window.getComputedStyle(element);

                return (
                    rect.width > 0 &&
                    rect.height > 0 &&
                    style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    style.opacity !== "0"
                );
            }

            function isDisabled(element) {
                return (
                    element.disabled === true ||
                    element.hasAttribute("disabled") ||
                    element.getAttribute(
                        "aria-disabled"
                    ) === "true"
                );
            }

            /*
            Trouver l'élément visible contenant seulement
            le compteur de records.
            */

            const recordCandidates =
                Array.from(
                    document.querySelectorAll("*")
                )
                .filter(element => {
                    if (!isVisible(element)) {
                        return false;
                    }

                    const text = (
                        element.innerText || ""
                    ).trim();

                    return (
                        /^\\d[\\d,\\.\\s]*\\s+records?$/i.test(
                            text
                        )
                    );
                })
                .sort((a, b) => {
                    const rectA =
                        a.getBoundingClientRect();

                    const rectB =
                        b.getBoundingClientRect();

                    return (
                        rectA.width * rectA.height
                        -
                        rectB.width * rectB.height
                    );
                });

            if (recordCandidates.length === 0) {
                return {
                    clicked: false,
                    reason:
                        "record_counter_not_found"
                };
            }

            const recordElement =
                recordCandidates[0];

            const recordRect =
                recordElement.getBoundingClientRect();

            /*
            Chercher un contrôle visible situé
            immédiatement à gauche du compteur.
            */

            const controls = Array.from(
                document.querySelectorAll(
                    [
                        "button",
                        "a",
                        '[role="button"]',
                        "[tabindex]"
                    ].join(",")
                )
            )
                .filter(element => {
                    if (
                        !isVisible(element) ||
                        isDisabled(element)
                    ) {
                        return false;
                    }

                    const rect =
                        element.getBoundingClientRect();

                    const recordCenterY =
                        recordRect.top +
                        recordRect.height / 2;

                    const controlCenterY =
                        rect.top +
                        rect.height / 2;

                    const verticallyAligned =
                        Math.abs(
                            controlCenterY -
                            recordCenterY
                        ) < 30;

                    const onLeft =
                        rect.right <=
                        recordRect.left + 10;

                    const closeToCounter =
                        recordRect.left -
                        rect.right < 80;

                    const reasonableSize =
                        rect.width > 0 &&
                        rect.height > 0 &&
                        rect.width <= 80 &&
                        rect.height <= 80;

                    return (
                        verticallyAligned &&
                        onLeft &&
                        closeToCounter &&
                        reasonableSize
                    );
                })
                .sort((a, b) => {
                    const rectA =
                        a.getBoundingClientRect();

                    const rectB =
                        b.getBoundingClientRect();

                    const distanceA =
                        recordRect.left -
                        rectA.right;

                    const distanceB =
                        recordRect.left -
                        rectB.right;

                    return (
                        distanceA - distanceB
                    );
                });

            if (controls.length === 0) {
                return {
                    clicked: false,
                    reason:
                        "pagination_toggle_not_found"
                };
            }

            controls[0].click();

            return {
                clicked: true,
                reason:
                    "closest_control_left_of_counter"
            };
        }
        """
    )

    if not result.get("clicked"):

        print(
            "Contrôle d'ouverture non détecté "
            "par sa structure."
        )

        print(
            "Deuxième tentative par position..."
        )

        fallback_clicked = page.evaluate(
            """
            () => {
                function isVisible(element) {
                    const rect =
                        element.getBoundingClientRect();

                    const style =
                        window.getComputedStyle(element);

                    return (
                        rect.width > 0 &&
                        rect.height > 0 &&
                        style.display !== "none" &&
                        style.visibility !== "hidden"
                    );
                }

                const recordCandidates =
                    Array.from(
                        document.querySelectorAll("*")
                    )
                    .filter(element => {
                        const text = (
                            element.innerText || ""
                        ).trim();

                        return (
                            isVisible(element) &&
                            /^\\d[\\d,\\.\\s]*\\s+records?$/i.test(
                                text
                            )
                        );
                    })
                    .sort((a, b) => {
                        const rectA =
                            a.getBoundingClientRect();

                        const rectB =
                            b.getBoundingClientRect();

                        return (
                            rectA.width * rectA.height
                            -
                            rectB.width * rectB.height
                        );
                    });

                if (recordCandidates.length === 0) {
                    return false;
                }

                const recordElement =
                    recordCandidates[0];

                const recordRect =
                    recordElement.getBoundingClientRect();

                /*
                Cliquer légèrement à gauche du compteur.
                */

                const x = Math.max(
                    5,
                    recordRect.left - 12
                );

                const y =
                    recordRect.top +
                    recordRect.height / 2;

                let target =
                    document.elementFromPoint(
                        x,
                        y
                    );

                if (!target) {
                    return false;
                }

                target =
                    target.closest(
                        [
                            "button",
                            "a",
                            '[role="button"]',
                            "[tabindex]"
                        ].join(",")
                    )
                    || target;

                target.click();

                return true;
            }
            """
        )

        if not fallback_clicked:

            raise RuntimeError(
                "Impossible de cliquer sur le contrôle "
                "situé à gauche du compteur de records."
            )

    try:

        page.wait_for_function(
            """
            () => {
                const elements = Array.from(
                    document.querySelectorAll("*")
                );

                return elements.some(element => {
                    const text = (
                        element.innerText || ""
                    ).trim();

                    const rect =
                        element.getBoundingClientRect();

                    return (
                        rect.width > 0 &&
                        rect.height > 0 &&
                        /^Page\\s+\\d+\\s+of\\s+\\d+$/i.test(
                            text
                        )
                    );
                });
            }
            """,
            timeout=15_000,
        )

    except Exception as error:

        raise RuntimeError(
            "Le contrôle d'ouverture a été cliqué, "
            "mais le panneau 'Page X of Y' "
            "ne s'est pas affiché."
        ) from error

    current_page, total_pages = (
        get_pagination_status(
            page
        )
    )

    print(
        f"Panneau ouvert : "
        f"Page {current_page} of "
        f"{total_pages}"
    )

    return True


def click_next_page_button(page):
    """
    Clique sur le contrôle Page suivante situé
    immédiatement à droite du texte visible :

        Page X of Y

    Cette version utilise directement la position du
    noeud texte "Page X of Y", plutôt que la position
    de son élément HTML parent.
    """

    if not pagination_panel_is_open(
        page
    ):

        print(
            "Le panneau de pagination est fermé. "
            "Réouverture..."
        )

        open_pagination_panel(
            page
        )

    result = page.evaluate(
        """
        () => {

            // =================================================
            // OUTILS
            // =================================================

            function isVisible(element) {

                if (!element) {
                    return false;
                }

                const rect =
                    element.getBoundingClientRect();

                const style =
                    window.getComputedStyle(element);

                return (
                    rect.width > 0 &&
                    rect.height > 0 &&
                    style.display !== "none" &&
                    style.visibility !== "hidden"
                );
            }


            function isDisabled(element) {

                if (!element) {
                    return true;
                }

                return (
                    element.disabled === true ||
                    element.hasAttribute("disabled") ||
                    element.getAttribute(
                        "aria-disabled"
                    ) === "true"
                );
            }


            function findClickableParent(element) {

                if (!element) {
                    return null;
                }

                let current = element;


                for (
                    let level = 0;
                    level < 8;
                    level++
                ) {

                    if (!current) {
                        break;
                    }


                    const style =
                        window.getComputedStyle(
                            current
                        );


                    const interactive =
                        current.tagName === "BUTTON"
                        ||
                        current.tagName === "A"
                        ||
                        current.getAttribute(
                            "role"
                        ) === "button"
                        ||
                        current.hasAttribute(
                            "tabindex"
                        )
                        ||
                        typeof current.onclick ===
                            "function"
                        ||
                        style.cursor === "pointer";


                    if (
                        interactive &&
                        !isDisabled(current)
                    ) {

                        return current;
                    }


                    current =
                        current.parentElement;
                }


                return null;
            }


            // =================================================
            // 1. TROUVER LE NOEUD TEXTE
            //
            // On cherche réellement :
            //
            //     Page 1 of 2
            //
            // au lieu de se fier au rectangle du parent HTML.
            // =================================================

            const walker =
                document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT
                );


            let textNode = null;
            let currentNode;


            while (
                currentNode =
                    walker.nextNode()
            ) {

                const text =
                    (
                        currentNode.nodeValue || ""
                    ).trim();


                if (
                    /^Page\\s+\\d+\\s+of\\s+\\d+$/i.test(
                        text
                    )
                ) {

                    const parent =
                        currentNode.parentElement;


                    if (
                        parent &&
                        isVisible(parent)
                    ) {

                        textNode =
                            currentNode;

                        break;
                    }
                }
            }


            if (!textNode) {

                return {
                    clicked: false,
                    reason:
                        "pagination_text_node_not_found"
                };
            }


            // =================================================
            // 2. OBTENIR LE RECTANGLE RÉEL DU TEXTE
            // =================================================

            const range =
                document.createRange();


            range.selectNodeContents(
                textNode
            );


            const textRect =
                range.getBoundingClientRect();


            if (
                textRect.width <= 0 ||
                textRect.height <= 0
            ) {

                return {
                    clicked: false,
                    reason:
                        "pagination_text_has_no_rectangle"
                };
            }


            // =================================================
            // 3. INFORMATIONS DE DIAGNOSTIC
            // =================================================

            const diagnostic = {

                text:
                    (
                        textNode.nodeValue || ""
                    ).trim(),

                left:
                    Math.round(
                        textRect.left
                    ),

                right:
                    Math.round(
                        textRect.right
                    ),

                top:
                    Math.round(
                        textRect.top
                    ),

                bottom:
                    Math.round(
                        textRect.bottom
                    ),

                width:
                    Math.round(
                        textRect.width
                    ),

                height:
                    Math.round(
                        textRect.height
                    )

            };


            // =================================================
            // 4. CHERCHER LES ÉLÉMENTS À DROITE DU TEXTE
            //
            // On teste plusieurs positions horizontales.
            // =================================================

            const centerY =
                textRect.top +
                textRect.height / 2;


            const offsets = [

                4,
                8,
                12,
                16,
                20,
                24,
                28,
                32,
                36,
                40,
                44,
                48,
                52,
                56,
                60

            ];


            for (const offset of offsets) {

                const x =
                    textRect.right +
                    offset;


                const elements =
                    document.elementsFromPoint(
                        x,
                        centerY
                    );


                for (
                    const element
                    of elements
                ) {

                    const clickable =
                        findClickableParent(
                            element
                        );


                    if (!clickable) {
                        continue;
                    }


                    /*
                    Éviter de cliquer sur le panneau
                    lui-même ou sur un élément énorme.
                    */

                    const rect =
                        clickable.getBoundingClientRect();


                    if (
                        rect.width <= 0 ||
                        rect.height <= 0
                    ) {
                        continue;
                    }


                    if (
                        rect.width > 100 ||
                        rect.height > 100
                    ) {
                        continue;
                    }


                    /*
                    Le contrôle Page suivante doit se
                    trouver à droite du texte.
                    */

                    if (
                        rect.right <
                        textRect.right
                    ) {
                        continue;
                    }


                    clickable.scrollIntoView({
                        block: "nearest",
                        inline: "nearest"
                    });


                    clickable.click();


                    return {

                        clicked: true,

                        reason:
                            "clicked_control_right_of_text",

                        paginationText:
                            diagnostic,

                        clickedTag:
                            clickable.tagName,

                        clickedLeft:
                            Math.round(
                                rect.left
                            ),

                        clickedRight:
                            Math.round(
                                rect.right
                            ),

                        clickedTop:
                            Math.round(
                                rect.top
                            ),

                        clickedWidth:
                            Math.round(
                                rect.width
                            ),

                        clickedHeight:
                            Math.round(
                                rect.height
                            ),

                        offset:
                            offset
                    };
                }
            }


            // =================================================
            // 5. FALLBACK
            //
            // Si elementsFromPoint ne trouve rien,
            // chercher tous les petits éléments interactifs
            // situés réellement à droite du texte.
            // =================================================

            const candidates =
                Array.from(
                    document.querySelectorAll("*")
                )
                .filter(element => {

                    if (!isVisible(element)) {
                        return false;
                    }


                    if (isDisabled(element)) {
                        return false;
                    }


                    const rect =
                        element.getBoundingClientRect();


                    const style =
                        window.getComputedStyle(
                            element
                        );


                    const interactive =
                        element.tagName ===
                            "BUTTON"
                        ||
                        element.tagName ===
                            "A"
                        ||
                        element.getAttribute(
                            "role"
                        ) === "button"
                        ||
                        element.hasAttribute(
                            "tabindex"
                        )
                        ||
                        typeof element.onclick ===
                            "function"
                        ||
                        style.cursor ===
                            "pointer";


                    if (!interactive) {
                        return false;
                    }


                    const elementCenterY =
                        rect.top +
                        rect.height / 2;


                    const verticallyAligned =
                        Math.abs(
                            elementCenterY -
                            centerY
                        ) < 30;


                    const onRight =
                        rect.left >=
                        textRect.right - 5;


                    const closeEnough =
                        rect.left -
                        textRect.right <
                        120;


                    const reasonableSize =
                        rect.width > 5
                        &&
                        rect.width < 100
                        &&
                        rect.height > 5
                        &&
                        rect.height < 100;


                    return (
                        verticallyAligned
                        &&
                        onRight
                        &&
                        closeEnough
                        &&
                        reasonableSize
                    );

                });


            // =================================================
            // 6. TRIER DE GAUCHE À DROITE
            // =================================================

            candidates.sort(
                (a, b) => {

                    return (
                        a.getBoundingClientRect().left
                        -
                        b.getBoundingClientRect().left
                    );

                }
            );


            // =================================================
            // 7. ÉLIMINER LES DOUBLONS HTML
            // =================================================

            const uniqueCandidates = [];


            for (
                const candidate
                of candidates
            ) {

                const rect =
                    candidate.getBoundingClientRect();


                const duplicate =
                    uniqueCandidates.some(
                        existing => {

                            const existingRect =
                                existing.getBoundingClientRect();


                            return (
                                Math.abs(
                                    existingRect.left -
                                    rect.left
                                ) < 3
                                &&
                                Math.abs(
                                    existingRect.top -
                                    rect.top
                                ) < 3
                            );

                        }
                    );


                if (!duplicate) {

                    uniqueCandidates.push(
                        candidate
                    );
                }
            }


            // =================================================
            // 8. PREMIER ÉLÉMENT À DROITE
            // =================================================

            if (
                uniqueCandidates.length > 0
            ) {

                const nextButton =
                    uniqueCandidates[0];


                const rect =
                    nextButton.getBoundingClientRect();


                nextButton.scrollIntoView({
                    block: "nearest",
                    inline: "nearest"
                });


                nextButton.click();


                return {

                    clicked: true,

                    reason:
                        "fallback_control_right_of_text",

                    paginationText:
                        diagnostic,

                    candidatesFound:
                        uniqueCandidates.length,

                    clickedTag:
                        nextButton.tagName,

                    clickedLeft:
                        Math.round(
                            rect.left
                        ),

                    clickedRight:
                        Math.round(
                            rect.right
                        ),

                    clickedWidth:
                        Math.round(
                            rect.width
                        ),

                    clickedHeight:
                        Math.round(
                            rect.height
                        )

                };
            }


            // =================================================
            // ÉCHEC
            // =================================================

            return {

                clicked: false,

                reason:
                    "next_page_control_not_found",

                paginationText:
                    diagnostic,

                candidatesFound:
                    uniqueCandidates.length

            };
        }
        """
    )


    print(
        "Résultat détection Page suivante : "
        f"{result}"
    )


    if not result.get(
        "clicked"
    ):

        return False


    print(
        "Bouton Page suivante cliqué."
    )

    return True
def wait_for_page_number(
    page,
    expected_page,
):

    page.wait_for_function(
        """
        expectedPage => {
            const elements = Array.from(
                document.querySelectorAll("*")
            );

            return elements.some(element => {
                const text = (
                    element.innerText || ""
                ).trim();

                const match = text.match(
                    /^Page\\s+(\\d+)\\s+of\\s+(\\d+)$/i
                );

                if (!match) {
                    return false;
                }

                const rect =
                    element.getBoundingClientRect();

                return (
                    rect.width > 0 &&
                    rect.height > 0 &&
                    Number(match[1]) ===
                    expectedPage
                );
            });
        }
        """,
        arg=expected_page,
        timeout=30_000,
    )


def wait_for_new_records_response(
    page,
    previous_response_count,
):

    for _ in range(60):

        page.wait_for_timeout(
            500
        )

        current_response_count = (
            count_records_query_responses()
        )

        if (
            current_response_count
            > previous_response_count
        ):
            return True

    return False


def load_all_pages(page):
    """
    Charge successivement toutes les pages Zapier.

    Séquence :

    1. Charger les lignes de la page actuelle.
    2. Ouvrir le panneau de pagination.
    3. Lire le texte Page X of Y.
    4. Cliquer sur Page suivante.
    5. Attendre le changement de page.
    6. Charger les lignes de la nouvelle page.
    7. Répéter jusqu'à la dernière page.
    """

    print("")
    print("=" * 60)
    print("PAGINATION ZAPIER")
    print("=" * 60)
    print("")

    # --------------------------------------------------------
    # Charger complètement la première page
    # --------------------------------------------------------

    print(
        "Chargement de la première page..."
    )

    scroll_current_page(
        page
    )

    # --------------------------------------------------------
    # Ouvrir le panneau de pagination
    # --------------------------------------------------------

    open_pagination_panel(
        page
    )

    current_page, total_pages = (
        get_pagination_status(
            page
        )
    )

    if (
        current_page is None
        or total_pages is None
    ):

        raise RuntimeError(
            "Impossible de lire la pagination "
            "après l'ouverture du panneau."
        )

    if total_pages > MAX_PAGES:

        raise RuntimeError(
            f"Nombre de pages anormalement élevé : "
            f"{total_pages}"
        )

    print(
        f"Pagination détectée : "
        f"Page {current_page} of "
        f"{total_pages}"
    )

    visited_pages = {
        current_page
    }

    # --------------------------------------------------------
    # Parcourir les pages suivantes
    # --------------------------------------------------------

    while current_page < total_pages:

        next_page = (
            current_page + 1
        )

        print("")
        print(
            f"Passage de la page "
            f"{current_page} "
            f"à la page {next_page}..."
        )

        previous_response_count = (
            count_records_query_responses()
        )

        if not pagination_panel_is_open(
            page
        ):

            open_pagination_panel(
                page
            )

        clicked = click_next_page_button(
            page
        )

        if not clicked:

            raise RuntimeError(
                "Impossible de cliquer sur le bouton "
                "Page suivante situé à droite de "
                "'Page X of Y'."
            )

        # ----------------------------------------------------
        # Attendre le changement du numéro de page
        # ----------------------------------------------------

        wait_for_page_number(
            page,
            next_page,
        )

        print(
            f"Zapier affiche maintenant : "
            f"Page {next_page} of "
            f"{total_pages}"
        )

        # ----------------------------------------------------
        # Attendre une nouvelle réponse réseau
        # ----------------------------------------------------

        response_received = (
            wait_for_new_records_response(
                page,
                previous_response_count,
            )
        )

        if response_received:

            print(
                "Nouvelle réponse "
                "/records/query reçue."
            )

        else:

            print(
                "AVERTISSEMENT : aucune nouvelle "
                "réponse /records/query détectée "
                "après le changement de page."
            )

        page.wait_for_timeout(
            WAIT_AFTER_PAGE_CHANGE_MS
        )

        # ----------------------------------------------------
        # Charger toutes les lignes de la nouvelle page
        # ----------------------------------------------------

        scroll_current_page(
            page
        )

        # ----------------------------------------------------
        # Rouvrir le panneau au besoin
        # ----------------------------------------------------

        if not pagination_panel_is_open(
            page
        ):

            open_pagination_panel(
                page
            )

        # ----------------------------------------------------
        # Confirmer le numéro de page
        # ----------------------------------------------------

        current_page, detected_total = (
            get_pagination_status(
                page
            )
        )

        if (
            current_page is None
            or detected_total is None
        ):

            raise RuntimeError(
                "Impossible de confirmer le numéro "
                "de la nouvelle page."
            )

        if current_page in visited_pages:

            raise RuntimeError(
                f"La page {current_page} a déjà été "
                "visitée. La pagination ne progresse pas."
            )

        visited_pages.add(
            current_page
        )

        total_pages = max(
            total_pages,
            detected_total,
        )

        if total_pages > MAX_PAGES:

            raise RuntimeError(
                f"Nombre de pages anormalement élevé : "
                f"{total_pages}"
            )

        print(
            f"Page confirmée : "
            f"{current_page} of "
            f"{total_pages}"
        )

    print("")
    print(
        "Toutes les pages Zapier "
        "ont été parcourues."
    )

    print(
        f"Pages visitées : "
        f"{len(visited_pages)}"
    )


# ============================================================
# DÉDOUBLONNAGE
# ============================================================

def deduplicate_records(candidates):

    best_by_key = {}

    for index, candidate in enumerate(
        candidates
    ):

        row = candidate["row"]
        score = candidate["score"]

        booking_id = row.get(
            "Booking ID",
            "",
        ).strip()

        # ----------------------------------------------------
        # CAS 1 : Booking ID commence par "Ex"
        #
        # ANCIENNE LOGIQUE CONSERVÉE :
        # toutes les lignes sont conservées grâce à index.
        # ----------------------------------------------------

        if booking_id.lower().startswith(
            "ex"
        ):

            unique_key = (
                "booking_id_ex",
                booking_id,
                index,
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

            unique_key = tuple(
                row.get(
                    column,
                    "",
                )
                for column in EXPECTED_COLUMNS
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
# DEBUG
# ============================================================

def write_debug_file():

    debug_content = {
        "table_id": TABLE_ID,
        "captured_response_count": len(
            captured_json
        ),
        "records_query_response_count": (
            count_records_query_responses()
        ),
        "recognized_fields": sorted(
            set(
                field_map.values()
            )
        ),
        "candidate_count": len(
            extracted_records
        ),
        "responses": captured_json,
    }

    try:

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

    except Exception as error:

        print(
            f"Erreur création debug : "
            f"{error}"
        )


def save_error_screenshot(page):

    try:

        page.screenshot(
            path=str(
                SCREENSHOT_FILE
            ),
            full_page=True,
        )

        print(
            f"Capture d'erreur : "
            f"{SCREENSHOT_FILE}"
        )

    except Exception as error:

        print(
            "Impossible de prendre la "
            f"capture d'écran : {error}"
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

            # ------------------------------------------------
            # Charger toutes les pages Zapier
            # ------------------------------------------------

            try:

                load_all_pages(
                    page
                )

            except Exception:

                save_error_screenshot(
                    page
                )

                raise

            browser.close()

    except Exception as error:

        print("")
        print("=" * 60)
        print("ERREUR PENDANT LA NAVIGATION")
        print("=" * 60)

        print(
            str(error)
        )

        write_debug_file()

        sys.exit(1)

    # --------------------------------------------------------
    # Analyse des réponses
    # --------------------------------------------------------

    print("")

    print(
        f"Réponses Zapier : "
        f"{len(captured_json)}"
    )

    print(
        f"Réponses /records/query : "
        f"{count_records_query_responses()}"
    )

    recognized_fields = {
        value
        for value
        in field_map.values()
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
                    f"records_query"
                    f"[{captured_index}]"
                ),
            )

    print(
        f"Enregistrements candidats : "
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
    # DEBUG
    # --------------------------------------------------------

    write_debug_file()

    # --------------------------------------------------------
    # Résultat
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("EXPORT TERMINÉ")
    print("=" * 60)

    print(
        f"Lignes : "
        f"{len(records)}"
    )

    print(
        f"Colonnes : "
        f"{len(EXPECTED_COLUMNS)}"
    )

    print(
        f"CSV : "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Debug : "
        f"{DEBUG_FILE}"
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
