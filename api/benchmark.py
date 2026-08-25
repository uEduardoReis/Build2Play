from flask import Flask, request, jsonify
import requests
import re
import statistics
import os

app = Flask(__name__)

YOUTUBE_API_KEY = os.environ.get(
    "YOUTUBE_API_KEY"
)

YOUTUBE_URL = \
    "https://www.googleapis.com/youtube/v3"


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


@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status":
            "GameBench YouTube API online"
    })


@app.route("/benchmark", methods=["POST"])
def benchmark():

    if not YOUTUBE_API_KEY:

        return jsonify({
            "error":
                "YOUTUBE_API_KEY não configurada."
        }), 500

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

    query = (
        f"{game} "
        f"{cpu} "
        f"{gpu} "
        f"{resolution} "
        f"{quality} "
        f"benchmark FPS"
    )

    try:

        search_results = \
            youtube_search(query)

        ids = []

        for item in search_results:

            video_id = item.get(
                "id",
                {}
            ).get(
                "videoId"
            )

            if video_id:

                ids.append(
                    video_id
                )

        videos = youtube_videos(
            ids
        )

        final_videos = []

        needs_comments = []

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

        # Comentários

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

                    comment_fps.extend(
                        extract_fps(text)
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

        # Média

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
            "error":
                str(e)
        }), 500