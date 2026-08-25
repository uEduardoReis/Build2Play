import os
import requests
import re

RAWG_API_KEY = os.environ.get("RAWG_API_KEY")

RAWG_URL = "https://api.rawg.io/api"


def rawg_search(game_name):

    response = requests.get(
        f"{RAWG_URL}/games",
        params={
            "key": RAWG_API_KEY,
            "search": game_name,
            "search_precise": "true",
            "page_size": 5
        },
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("results"):
        return None

    return data["results"][0]


def rawg_game(game_id):

    response = requests.get(
        f"{RAWG_URL}/games/{game_id}",
        params={
            "key": RAWG_API_KEY
        },
        timeout=15
    )

    response.raise_for_status()

    return response.json()


def get_pc_requirements(game):

    minimum = None
    recommended = None

    for platform in game.get("platforms", []):

        platform_info = platform.get(
            "platform",
            {}
        )

        if platform_info.get("slug") == "pc":

            requirements = platform.get(
                "requirements",
                {}
            )

            minimum = requirements.get("minimum")
            recommended = requirements.get("recommended")

            break

    return minimum, recommended


def parse_requirements(text):

    result = {
        "cpu": None,
        "gpu": None,
        "ram": None,
        "storage": None
    }

    if not text:
        return result

    lines = text.replace(
        "\r",
        "\n"
    ).split("\n")

    for line in lines:

        line = line.strip()

        if not line:
            continue

        lower = line.lower()

        if any(x in lower for x in [
            "processor",
            "cpu",
            "intel core",
            "amd ryzen"
        ]):

            value = (
                line.split(":", 1)[1].strip()
                if ":" in line
                else line
            )

            if not result["cpu"]:
                result["cpu"] = value

        elif any(x in lower for x in [
            "graphics",
            "gpu",
            "video card",
            "nvidia geforce",
            "geforce",
            "radeon"
        ]):

            value = (
                line.split(":", 1)[1].strip()
                if ":" in line
                else line
            )

            if not result["gpu"]:
                result["gpu"] = value

        elif (
            "memory" in lower
            or "ram" in lower
        ):

            match = re.search(
                r"(\d+)\s*gb",
                lower
            )

            if match:
                result["ram"] = int(
                    match.group(1)
                )

        elif (
            "storage" in lower
            or "hard drive" in lower
            or "hard disk" in lower
        ):

            match = re.search(
                r"(\d+)\s*(gb|tb)",
                lower
            )

            if match:

                value = int(
                    match.group(1)
                )

                if match.group(2) == "tb":
                    value *= 1024

                result["storage"] = value

    return result


def handler(request):

    if request.method != "POST":

        return {
            "error": "Method not allowed"
        }, 405

    if not RAWG_API_KEY:

        return {
            "error": "RAWG_API_KEY não configurada"
        }, 500

    data = request.get_json()

    names = data.get(
        "games",
        []
    )

    requirement_type = data.get(
        "requirement_type",
        "recommended"
    )

    results = []

    for name in names[:3]:

        try:

            search = rawg_search(name)

            if not search:

                results.append({
                    "name": name,
                    "error":
                        "Jogo não encontrado."
                })

                continue

            game = rawg_game(
                search["id"]
            )

            minimum_raw, recommended_raw = \
                get_pc_requirements(game)

            minimum = parse_requirements(
                minimum_raw
            )

            recommended = parse_requirements(
                recommended_raw
            )

            selected = (
                minimum
                if requirement_type == "minimum"
                else recommended
            )

            results.append({

                "name":
                    game.get(
                        "name",
                        name
                    ),

                "image":
                    game.get(
                        "background_image"
                    ),

                "minimum":
                    minimum,

                "recommended":
                    recommended,

                "selected":
                    selected

            })

        except Exception as e:

            results.append({

                "name":
                    name,

                "error":
                    str(e)

            })

    return {
        "games": results,
        "requirement_type": requirement_type
    }