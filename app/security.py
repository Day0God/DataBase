import hashlib
import hmac
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from .errors import ApiError, ensure


def normalize_username(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def username_key(value):
    return normalize_username(value).casefold()


def validate_credentials(username_value, password):
    username = normalize_username(username_value)
    ensure(
        re.fullmatch(r"[\w-]{3,30}", username, flags=re.UNICODE) is not None,
        422,
        "VALIDATION_ERROR",
        "用户名须为 3 到 30 个字母、数字、汉字、下划线或短横线",
    )
    ensure(
        isinstance(password, str) and 8 <= len(password) <= 72,
        422,
        "VALIDATION_ERROR",
        "密码长度须为 8 到 72 个字符",
    )
    return username, password


def hash_password(password):
    return generate_password_hash(password, method="scrypt")


def verify_password(password, password_hash):
    return check_password_hash(password_hash, password)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db, user_id):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=current_app.config["SESSION_DAYS"])
    db.sessions.insert_one(
        {
            "tokenHash": hash_token(token),
            "userId": user_id,
            "createdAt": now,
            "expiresAt": expires_at,
        }
    )
    return token


def set_session_cookie(response, token):
    response.set_cookie(
        current_app.config["COOKIE_NAME"],
        token,
        max_age=current_app.config["SESSION_DAYS"] * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
        secure=current_app.config["SECURE_COOKIES"],
        path="/",
    )
    return response


def clear_session_cookie(response):
    response.delete_cookie(
        current_app.config["COOKIE_NAME"],
        path="/",
        httponly=True,
        samesite="Lax",
        secure=current_app.config["SECURE_COOKIES"],
    )
    return response


def user_from_request(db):
    token = request.cookies.get(current_app.config["COOKIE_NAME"])
    if not token:
        return None
    session = db.sessions.find_one(
        {
            "tokenHash": hash_token(token),
            "expiresAt": {"$gt": datetime.now(timezone.utc)},
        }
    )
    if not session:
        return None
    return db.users.find_one({"_id": session["userId"]})


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = user_from_request(current_app.extensions["mongo_db"])
        if not user:
            raise ApiError(401, "AUTH_REQUIRED", "请先登录")
        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


def participant_key(survey_id, user_id):
    message = f"{survey_id}:{user_id}".encode("utf-8")
    return hmac.new(
        current_app.config["RESPONDENT_SECRET"].encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
