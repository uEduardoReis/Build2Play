from flask import Flask, render_template, request, jsonify
import requests
import re
import statistics

app = Flask(__name__)

RAWG_API_KEY = "COLOQUE_SUA_CHAVE_RAWG_AQUI"
YOUTUBE_API_KEY = "COLOQUE_SUA_CHAVE_YOUTUBE_AQUI"

RAWG_URL = "https://api.rawg.io/api"
YOUTUBE_URL = "https://www.googleapis.com/youtube/v3"


@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------
# RAWG
# ---------------------------------------------------------

def search_rawg_game(game_name):
    url = f"{RAWG_URL}/games"

    params = {
        "key": RAWG_API_KEY,
        "search": game_name,
        "search_precise": "true",
        "page_size": 5
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()

    if not data.get("results"):
        return None

    return data["results"][0]


def get_rawg_game(game_id):
    url = f"{RAWG_URL}/games/{game_id}"

    params = {
        "key": RAWG_API_KEY
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    return response.json()


def extract_pc_requirements(game):
    minimum = None
    recommended = None

    for platform_data in game.get("platforms", []):
        platform = platform_data.get("platform", {})

        if platform.get("slug") != "pc":
            continue

        requirements = platform_data.get("requirements") or {}

        minimum = requirements.get("minimum")
        recommended = requirements.get("recommended")

        break

    return {
        "minimum": minimum,
        "recommended": recommended
    }


# ---------------------------------------------------------
# PARSER DOS REQUISITOS
# ---------------------------------------------------------

def parse_requirement_text(text):
    if not text:
        return {
            "cpu": None,
            "gpu": None,
            "ram": None,
            "storage": None
        }

    text = text.replace("\r", "\n")

    result = {
        "cpu": None,
        "gpu": None,
        "ram": None,
        "storage": None
    }

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    for line in lines:

        lower = line.lower()

        if any(x in lower for x in [
            "processor",
            "cpu",
            "intel core",
            "amd ryzen"
        ]):
            if ":" in line:
                result["cpu"] = line.split(":", 1)[1].strip()
            else:
                result["cpu"] = line

        elif any(x in lower for x in [
            "graphics",
            "gpu",
            "video card",
            "nvidia geforce",
            "amd radeon",
            "radeon",
            "geforce"
        ]):
            if ":" in line:
                result["gpu"] = line.split(":", 1)[1].strip()
            else:
                result["gpu"] = line

        elif "memory" in lower or "ram" in lower:
            match = re.search(r"(\d+)\s*gb", lower)

            if match:
                result["ram"] = int(match.group(1))

        elif "storage" in lower or "hard drive" in lower:
            match = re.search(r"(\d+)\s*(gb|tb)", lower)

            if match:
                value = int(match.group(1))

                if match.group(2) == "tb":
                    value *= 1024

                result["storage"] = value

    return result


# ---------------------------------------------------------
# YOUTUBE
# ---------------------------------------------------------

def search_youtube(query):

    url = f"{YOUTUBE_URL}/search"

    params = {
        "key": YOUTUBE_API_KEY,
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 10,
        "order": "relevance"
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    return response.json().get("items", [])


def get_youtube_videos(video_ids):

    if not video_ids:
        return []

    url = f"{YOUTUBE_URL}/videos"

    params = {
        "key": YOUTUBE_API_KEY,
        "part": "snippet,contentDetails,statistics",
        "id": ",".join(video_ids)
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    return response.json().get("items", [])


# ---------------------------------------------------------
# EXTRAÇÃO DE FPS
# ---------------------------------------------------------

def extract_fps(text):

    if not text:
        return []

    patterns = [

        # Average FPS: 72
        r"(?:average|avg|average fps|avg fps)"
        r"[^0-9]{0,20}"
        r"(\d+(?:\.\d+)?)\s*fps",

        # 72 FPS
        r"(\d+(?:\.\d+)?)\s*fps",

        # FPS: 72
        r"fps"
        r"[^0-9]{0,10}"
        r"(\d+(?:\.\d+)?)"
    ]

    values = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        for value in matches:

            try:
                fps = float(value)

                # Evita números absurdos
                if 10 <= fps <= 300:
                    values.append(fps)

            except ValueError:
                pass

    # Remove duplicados
    return sorted(set(values))


# ---------------------------------------------------------
# API: BUSCAR JOGOS
# ---------------------------------------------------------

@app.post("/api/games")
def api_games():

    data = request.json

    games = data.get("games", [])

    if not games:
        return jsonify({
            "error": "Nenhum jogo informado."
        }), 400

    results = []

    for game_name in games[:3]:

        try:

            search_result = search_rawg_game(game_name)

            if not search_result:
                results.append({
                    "query": game_name,
                    "error": "Jogo não encontrado."
                })

                continue

            game = get_rawg_game(search_result["id"])

            requirements = extract_pc_requirements(game)

            minimum = parse_requirement_text(
                requirements["minimum"]
            )

            recommended = parse_requirement_text(
                requirements["recommended"]
            )

            results.append({
                "query": game_name,
                "id": game["id"],
                "name": game["name"],
                "image": game.get("background_image"),
                "minimum_raw": requirements["minimum"],
                "recommended_raw": requirements["recommended"],
                "minimum": minimum,
                "recommended": recommended
            })

        except Exception as e:

            results.append({
                "query": game_name,
                "error": str(e)
            })

    return jsonify({
        "games": results
    })


# ---------------------------------------------------------
# API: RECOMENDAÇÃO DO PC
# ---------------------------------------------------------

@app.post("/api/recommend")
def recommend():

    data = request.json

    games = data.get("games", [])

    # Esta versão usa uma regra simples:
    # pega o último requisito informado para cada componente.
    #
    # Posteriormente podemos criar um comparador real
    # de CPUs e GPUs.

    cpu = None
    gpu = None
    ram = 0
    storage = 0

    sources = []

    for game in games:

        recommended = game.get("recommended", {})

        if recommended.get("cpu"):
            cpu = recommended["cpu"]
            sources.append(
                f"CPU de {game['name']}"
            )

        if recommended.get("gpu"):
            gpu = recommended["gpu"]
            sources.append(
                f"GPU de {game['name']}"
            )

        if recommended.get("ram"):
            ram = max(
                ram,
                int(recommended["ram"])
            )

        if recommended.get("storage"):
            storage = max(
                storage,
                int(recommended["storage"])
            )

    return jsonify({
        "cpu": cpu or "Não encontrado",
        "gpu": gpu or "Não encontrado",
        "ram": ram or None,
        "storage": storage or None,
        "sources": sources
    })


# ---------------------------------------------------------
# API: BENCHMARK
# ---------------------------------------------------------

@app.post("/api/benchmark")
def benchmark():

    data = request.json

    game = data.get("game", "")
    cpu = data.get("cpu", "")
    gpu = data.get("gpu", "")
    ram = data.get("ram", "")
    resolution = data.get("resolution", "1080p")
    quality = data.get("quality", "High")
    target_fps = float(data.get("target_fps", 60))

    query = (
        f"{game} "
        f"{cpu} "
        f"{gpu} "
        f"{resolution} "
        f"{quality} "
        f"benchmark FPS"
    )

    try:

        search_results = search_youtube(query)

        video_ids = []

        for item in search_results:

            video_id = (
                item
                .get("id", {})
                .get("videoId")
            )

            if video_id:
                video_ids.append(video_id)

        videos = get_youtube_videos(video_ids)

        benchmark_results = []

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

            combined_text = (
                title + "\n" + description
            )

            fps_values = extract_fps(
                combined_text
            )

            benchmark_results.append({
                "id": video["id"],
                "title": title,
                "description": description[:500],
                "channel": snippet.get(
                    "channelTitle"
                ),
                "published": snippet.get(
                    "publishedAt"
                ),
                "thumbnail":
                    snippet
                    .get("thumbnails", {})
                    .get("medium", {})
                    .get("url"),
                "fps": fps_values
            })

        all_fps = []

        for video in benchmark_results:
            all_fps.extend(video["fps"])

        average = None

        if all_fps:
            average = statistics.mean(
                all_fps
            )

        if average is None:

            verdict = (
                "Não foi possível extrair FPS "
                "automaticamente."
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

            "query": query,

            "configuration": {
                "game": game,
                "cpu": cpu,
                "gpu": gpu,
                "ram": ram,
                "resolution": resolution,
                "quality": quality,
                "target_fps": target_fps
            },

            "average_fps": average,

            "fps_samples": all_fps,

            "verdict": verdict,

            "videos": benchmark_results

        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )