from flask import Flask, request, jsonify
import requests
import re
import statistics
import os

app = Flask(__name__)

# ==========================================================
# API KEYS
# ==========================================================

RAWG_API_KEY = os.environ.get("RAWG_API_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

RAWG_URL = "https://api.rawg.io/api"
YOUTUBE_URL = "https://www.googleapis.com/youtube/v3"


# ==========================================================
# RAWG
# ==========================================================

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


# ==========================================================
# REQUISITOS
# ==========================================================

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

            minimum = requirements.get(
                "minimum"
            )

            recommended = requirements.get(
                "recommended"
            )

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

        # CPU
        if any(x in lower for x in [
            "processor",
            "cpu",
            "intel core",
            "amd ryzen"
        ]):

            if ":" in line:
                value = line.split(
                    ":",
                    1
                )[1].strip()
            else:
                value = line

            if not result["cpu"]:
                result["cpu"] = value

        # GPU
        elif any(x in lower for x in [
            "graphics",
            "gpu",
            "video card",
            "nvidia geforce",
            "geforce",
            "radeon"
        ]):

            if ":" in line:
                value = line.split(
                    ":",
                    1
                )[1].strip()
            else:
                value = line

            if not result["gpu"]:
                result["gpu"] = value

        # RAM
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

        # STORAGE
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


# ==========================================================
# JOGOS
# ==========================================================

@app.route("/api/games", methods=["POST"])
def games():

    data = request.get_json()

    names = data.get(
        "games",
        []
    )

    requirement_type = data.get(
        "requirement_type",
        "recommended"
    )

    if not RAWG_API_KEY:

        return jsonify({
            "error":
                "RAWG_API_KEY não configurada."
        }), 500

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

                "name": name,

                "error": str(e)

            })

    return jsonify({

        "games": results,

        "requirement_type":
            requirement_type

    })


# ==========================================================
# YOUTUBE
# ==========================================================

def youtube_search(query):

    response = requests.get(
        f"{YOUTUBE_URL}/search",
        params={

            "key":
                YOUTUBE_API_KEY,

            "part":
                "snippet",

            "q":
                query,

            "type":
                "video",

            "maxResults":
                10,

            "order":
                "relevance"

        },
        timeout=15
    )

    response.raise_for_status()

    return response.json().get(
        "items",
        []
    )


def youtube_videos(ids):

    if not ids:
        return []

    response = requests.get(

        f"{YOUTUBE_URL}/videos",

        params={

            "key":
                YOUTUBE_API_KEY,

            "part":
                "snippet",

            "id":
                ",".join(ids)

        },

        timeout=15
    )

    response.raise_for_status()

    return response.json().get(
        "items",
        []
    )


# ==========================================================
# COMENTÁRIOS
# ==========================================================

def youtube_comments(video_id):

    try:

        response = requests.get(

            f"{YOUTUBE_URL}/commentThreads",

            params={

                "key":
                    YOUTUBE_API_KEY,

                "part":
                    "snippet",

                "videoId":
                    video_id,

                "maxResults":
                    50,

                "order":
                    "relevance",

                "textFormat":
                    "plainText"

            },

            timeout=15
        )

        if response.status_code != 200:
            return []

        return response.json().get(
            "items",
            []
        )

    except Exception:

        return []


# ==========================================================
# FPS
# ==========================================================

def extract_fps(text):

    if not text:
        return []

    patterns = [

        r"(?:average|avg|mean)"
        r"[^0-9]{0,30}"
        r"(\d+(?:\.\d+)?)"
        r"\s*fps",

        r"(\d+(?:\.\d+)?)"
        r"\s*fps"
        r"[^a-z]{0,20}"
        r"(?:average|avg|mean)",

        r"(?:around|about|roughly)"
        r"[^0-9]{0,10}"
        r"(\d+(?:\.\d+)?)"
        r"\s*fps",

        r"(?:getting|running|runs)"
        r"[^0-9]{0,20}"
        r"(\d+(?:\.\d+)?)"
        r"\s*fps",

        r"fps"
        r"[^0-9]{0,10}"
        r"(\d+(?:\.\d+)?)"

    ]

    values = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            re.IGNORECASE
        )

        for value in matches:

            try:

                fps = float(value)

                if 15 <= fps <= 300:

                    values.append(fps)

            except ValueError:

                pass

    return sorted(
        set(values)
    )


# ==========================================================
# BENCHMARK
# ==========================================================

@app.route("/api/benchmark", methods=["POST"])
def benchmark():

    data = request.get_json()

    game = data.get(
        "game",
        ""
    )

    cpu = data.get(
        "cpu",
        ""
    )

    gpu = data.get(
        "gpu",
        ""
    )

    ram = data.get(
        "ram",
        ""
    )

    resolution = data.get(
        "resolution",
        "1080p"
    )

    quality = data.get(
        "quality",
        "High"
    )

    target_fps = float(
        data.get(
            "target_fps",
            60
        )
    )

    if not YOUTUBE_API_KEY:

        return jsonify({
            "error":
                "YOUTUBE_API_KEY não configurada."
        }), 500

    query = (
        f"{game} "
        f"{cpu} "
        f"{gpu} "
        f"{resolution} "
        f"{quality} "
        f"benchmark FPS"
    )

    try:

        search_results = youtube_search(
            query
        )

        ids = []

        for item in search_results:

            video_id = item.get(
                "id",
                {}
            ).get(
                "videoId"
            )

            if video_id:
                ids.append(video_id)

        videos = youtube_videos(
            ids
        )

        final_videos = []

        needs_comments = []

        # ==================================================
        # TÍTULO + DESCRIÇÃO
        # ==================================================

        for video in videos:

            snippet = video.get(
                "snippet",
                {}
            )

            title = snippet.get(
                "title",
                ""
            )

            description = snippet.get(
                "description",
                ""
            )

            text = (
                title
                + "\n"
                + description
            )

            fps = extract_fps(
                text
            )

            result = {

                "id":
                    video["id"],

                "title":
                    title,

                "channel":
                    snippet.get(
                        "channelTitle",
                        ""
                    ),

                "thumbnail":
                    snippet.get(
                        "thumbnails",
                        {}
                    ).get(
                        "medium",
                        {}
                    ).get(
                        "url"
                    ),

                "fps":
                    fps,

                "source":
                    "description"

            }

            if fps:

                final_videos.append(
                    result
                )

            else:

                needs_comments.append(
                    result
                )

        # ==================================================
        # COMENTÁRIOS
        # ==================================================

        for result in needs_comments:

            comments = youtube_comments(
                result["id"]
            )

            comment_fps = []

            for comment in comments:

                try:

                    text = comment[
                        "snippet"
                    ][
                        "topLevelComment"
                    ][
                        "snippet"
                    ][
                        "textDisplay"
                    ]

                    values = extract_fps(
                        text
                    )

                    comment_fps.extend(
                        values
                    )

                except (KeyError, TypeError):

                    pass

            if comment_fps:

                result["fps"] = sorted(
                    set(comment_fps)
                )

                result["source"] = \
                    "comments"

                final_videos.append(
                    result
                )

        # ==================================================
        # MÉDIA
        # ==================================================

        all_fps = []

        for video in final_videos:

            all_fps.extend(
                video["fps"]
            )

        average = None

        if all_fps:

            average = statistics.mean(
                all_fps
            )

        # ==================================================
        # VEREDITO
        # ==================================================

        if average is None:

            verdict = (
                "Não foram encontrados "
                "dados suficientes."
            )

        elif average >= target_fps:

            verdict = (
                f"Provavelmente atinge "
                f"{target_fps:.0f} FPS."
            )

        else:

            verdict = (
                f"Provavelmente fica abaixo "
                f"de {target_fps:.0f} FPS."
            )

        return jsonify({

            "query":
                query,

            "average_fps":
                average,

            "verdict":
                verdict,

            "videos":
                final_videos

        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500