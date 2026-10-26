from bson import ObjectId
from datetime import date, datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from pymongo import MongoClient
from werkzeug.exceptions import HTTPException

from .config import Config
from .errors import ApiError
from .routes import api
from .schema import initialize_database


PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"


def _json_default(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def create_app(database=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    app.json.default = _json_default

    if database is None:
        client = MongoClient(
            app.config["MONGODB_URI"],
            serverSelectionTimeoutMS=5000,
            tz_aware=True,
        )
        database = client.get_default_database()
        app.extensions["mongo_client"] = client

    initialize_database(database)
    app.extensions["mongo_db"] = database
    app.register_blueprint(api)

    @app.before_request
    def enforce_json_for_api_mutations():
        if (
            request.path.startswith("/api/")
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and not request.is_json
        ):
            raise ApiError(
                415,
                "UNSUPPORTED_MEDIA_TYPE",
                "请求必须使用 application/json",
            )

    @app.after_request
    def apply_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'self'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    @app.get("/login")
    @app.get("/register")
    def home():
        return send_from_directory(PUBLIC_DIR, "index.html")

    @app.get("/survey/<slug>")
    def survey_page(slug):
        return send_from_directory(PUBLIC_DIR, "survey.html")

    @app.get("/builder/<survey_id>")
    def builder_page(survey_id):
        return send_from_directory(PUBLIC_DIR, "builder.html")

    @app.get("/stats/<survey_id>")
    def stats_page(survey_id):
        return send_from_directory(PUBLIC_DIR, "stats.html")

    @app.get("/library")
    def library_page():
        return send_from_directory(PUBLIC_DIR, "library.html")

    @app.get("/css/<path:filename>")
    def css_files(filename):
        return send_from_directory(PUBLIC_DIR / "css", filename)

    @app.get("/js/<path:filename>")
    def js_files(filename):
        return send_from_directory(PUBLIC_DIR / "js", filename)

    @app.get("/favicon.svg")
    def favicon():
        return send_from_directory(PUBLIC_DIR, "favicon.svg")

    @app.errorhandler(ApiError)
    def handle_api_error(error):
        payload = {"code": error.code, "message": error.message}
        if error.details:
            payload["details"] = error.details
        return jsonify({"error": payload}), error.status

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "error": {
                            "code": error.name.upper().replace(" ", "_"),
                            "message": error.description,
                        }
                    }
                ),
                error.code,
            )
        return error

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.exception("Unhandled exception", exc_info=error)
        return (
            jsonify(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "服务器内部错误",
                    }
                }
            ),
            500,
        )

    return app
