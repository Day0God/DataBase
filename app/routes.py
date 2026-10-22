import math
import re
import secrets
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, g, jsonify, request
from pymongo.errors import DuplicateKeyError

from .errors import ApiError, ensure
from .security import (
    clear_session_cookie,
    create_session,
    hash_password,
    hash_token,
    participant_key,
    require_auth,
    set_session_cookie,
    user_from_request,
    username_key,
    validate_credentials,
    verify_password,
)
from .validation import (
    evaluate_submission,
    normalize_questions,
    validate_survey_fields,
)

api = Blueprint("api", __name__, url_prefix="/api")


def db():
    return __import__("flask").current_app.extensions["mongo_db"]


def ok(data, status=200):
    return jsonify({"data": data}), status


def json_body():
    data = request.get_json(silent=False)
    ensure(
        isinstance(data, dict),
        422,
        "VALIDATION_ERROR",
        "请求体必须是 JSON 对象",
    )
    return data


def object_id(value, label="资源"):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise ApiError(404, "NOT_FOUND", f"{label}不存在") from None


def public_user(user):
    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "createdAt": user["createdAt"],
    }


def public_question(question):
    return {
        "id": question["id"],
        "type": question["type"],
        "title": question["title"],
        "required": question["required"],
        "order": question["order"],
        "options": question.get("options", []),
        "validation": question.get("validation", {}),
        "jumps": question.get("jumps", []),
    }


def questions_for_survey(survey_id):
    return list(db().questions.find({"surveyId": survey_id}).sort("order", 1))


def owned_survey(survey_id_input):
    survey_id = object_id(survey_id_input, "问卷")
    survey = db().surveys.find_one(
        {"_id": survey_id, "ownerId": g.current_user["_id"]}
    )
    if not survey:
        raise ApiError(404, "NOT_FOUND", "问卷不存在")
    return survey


def survey_summary(survey, submission_count=0):
    return {
        "id": str(survey["_id"]),
        "title": survey["title"],
        "description": survey["description"],
        "slug": survey["slug"],
        "status": survey["status"],
        "allowAnonymous": survey["allowAnonymous"],
        "allowMultipleResponses": survey["allowMultipleResponses"],
        "closesAt": survey.get("closesAt"),
        "publishedAt": survey.get("publishedAt"),
        "closedAt": survey.get("closedAt"),
        "createdAt": survey["createdAt"],
        "updatedAt": survey["updatedAt"],
        "submissionCount": submission_count,
        "hasResponses": submission_count > 0,
        "publicPath": f"/survey/{survey['slug']}",
    }


def has_submissions(survey_id):
    return (
        db().submissions.find_one(
            {"surveyId": survey_id},
            {"_id": 1},
        )
        is not None
    )


@api.get("/health")
def health():
    db().command("ping")
    return ok({"status": "ok"})


@api.post("/auth/register")
def register():
    data = json_body()
    username, password = validate_credentials(
        data.get("username"),
        data.get("password"),
    )
    now = datetime.now(timezone.utc)
    user = {
        "username": username,
        "usernameKey": username_key(username),
        "passwordHash": hash_password(password),
        "createdAt": now,
    }
    try:
        inserted = db().users.insert_one(user)
    except DuplicateKeyError:
        raise ApiError(409, "USERNAME_TAKEN", "用户名已被使用") from None
    user["_id"] = inserted.inserted_id
    token = create_session(db(), inserted.inserted_id)
    response = jsonify({"data": {"user": public_user(user)}})
    response.status_code = 201
    return set_session_cookie(response, token)


@api.post("/auth/login")
def login():
    data = json_body()
    username, password = validate_credentials(
        data.get("username"),
        data.get("password"),
    )
    user = db().users.find_one({"usernameKey": username_key(username)})
    if not user or not verify_password(password, user["passwordHash"]):
        raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码错误")
    token = create_session(db(), user["_id"])
    response = jsonify({"data": {"user": public_user(user)}})
    return set_session_cookie(response, token)


@api.post("/auth/logout")
def logout():
    token = request.cookies.get(__import__("flask").current_app.config["COOKIE_NAME"])
    if token:
        db().sessions.delete_one({"tokenHash": hash_token(token)})
    return clear_session_cookie(ok({"loggedOut": True})[0])


@api.get("/auth/me")
@require_auth
def me():
    return ok({"user": public_user(g.current_user)})


@api.get("/surveys")
@require_auth
def list_surveys():
    surveys = list(
        db().surveys.find({"ownerId": g.current_user["_id"]}).sort("createdAt", -1)
    )
    ids = [survey["_id"] for survey in surveys]
    counts = {}
    if ids:
        rows = db().submissions.aggregate(
            [
                {"$match": {"surveyId": {"$in": ids}}},
                {"$group": {"_id": "$surveyId", "count": {"$sum": 1}}},
            ]
        )
        counts = {str(row["_id"]): row["count"] for row in rows}
    return ok(
        [
            survey_summary(survey, counts.get(str(survey["_id"]), 0))
            for survey in surveys
        ]
    )


@api.post("/surveys")
@require_auth
def create_survey():
    fields = validate_survey_fields(json_body())
    slug = None
    for _ in range(5):
        candidate = secrets.token_urlsafe(9)
        if not db().surveys.find_one({"slug": candidate}, {"_id": 1}):
            slug = candidate
            break
    ensure(slug, 500, "SLUG_GENERATION_FAILED", "无法生成问卷链接，请重试")
    now = datetime.now(timezone.utc)
    survey = {
        "ownerId": g.current_user["_id"],
        "title": fields["title"],
        "description": fields["description"],
        "slug": slug,
        "status": "draft",
        "allowAnonymous": fields["allowAnonymous"],
        "allowMultipleResponses": fields["allowMultipleResponses"],
        "closesAt": fields.get("closesAt"),
        "publishedAt": None,
        "closedAt": None,
        "version": 1,
        "createdAt": now,
        "updatedAt": now,
    }
    inserted = db().surveys.insert_one(survey)
    survey["_id"] = inserted.inserted_id
    return ok(survey_summary(survey), 201)


@api.get("/surveys/<survey_id>")
@require_auth
def get_survey(survey_id):
    survey = owned_survey(survey_id)
    submission_count = db().submissions.count_documents(
        {"surveyId": survey["_id"]}
    )
    return ok(
        {
            "survey": survey_summary(survey, submission_count),
            "questions": [
                public_question(question)
                for question in questions_for_survey(survey["_id"])
            ],
        }
    )


@api.patch("/surveys/<survey_id>")
@require_auth
def update_survey(survey_id):
    survey = owned_survey(survey_id)
    fields = validate_survey_fields(json_body(), partial=True)
    ensure(fields, 422, "VALIDATION_ERROR", "没有可更新的字段")
    if (
        fields.get("closesAt")
        and survey["status"] == "published"
        and fields["closesAt"] <= datetime.now(timezone.utc)
    ):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "发布中的问卷截止时间必须晚于当前时间",
        )
    fields["updatedAt"] = datetime.now(timezone.utc)
    result = db().surveys.find_one_and_update(
        {"_id": survey["_id"], "ownerId": g.current_user["_id"]},
        {"$set": fields, "$inc": {"version": 1}},
        return_document=True,
    )
    submission_count = db().submissions.count_documents(
        {"surveyId": survey["_id"]}
    )
    return ok(survey_summary(result, submission_count))


@api.put("/surveys/<survey_id>/questions")
@require_auth
def save_questions(survey_id):
    survey = owned_survey(survey_id)
    ensure(
        survey["status"] != "published",
        409,
        "SURVEY_PUBLISHED",
        "请先关闭问卷，再修改题目",
    )
    ensure(
        not has_submissions(survey["_id"]),
        409,
        "SURVEY_HAS_RESPONSES",
        "已有回答的问卷不能修改题目",
    )
    questions = normalize_questions(json_body().get("questions"))
    now = datetime.now(timezone.utc)
    documents = [
        {**question, "surveyId": survey["_id"], "createdAt": now}
        for question in questions
    ]
    db().questions.delete_many({"surveyId": survey["_id"]})
    if documents:
        db().questions.insert_many(documents)
    db().surveys.update_one(
        {"_id": survey["_id"]},
        {"$set": {"updatedAt": now}, "$inc": {"version": 1}},
    )
    return ok([public_question(question) for question in documents])


@api.post("/surveys/<survey_id>/publish")
@require_auth
def publish_survey(survey_id):
    survey = owned_survey(survey_id)
    questions = questions_for_survey(survey["_id"])
    ensure(
        questions,
        422,
        "SURVEY_HAS_NO_QUESTIONS",
        "至少添加一道题后才能发布",
    )
    now = datetime.now(timezone.utc)
    if survey.get("closesAt") and survey["closesAt"] <= now:
        raise ApiError(
            422,
            "SURVEY_DEADLINE_PASSED",
            "问卷截止时间已过，请先设置新的截止时间",
        )
    result = db().surveys.find_one_and_update(
        {"_id": survey["_id"], "ownerId": g.current_user["_id"]},
        {
            "$set": {
                "status": "published",
                "closedAt": None,
                "publishedAt": survey.get("publishedAt") or now,
                "updatedAt": now,
            },
            "$inc": {"version": 1},
        },
        return_document=True,
    )
    submission_count = db().submissions.count_documents(
        {"surveyId": survey["_id"]}
    )
    return ok(survey_summary(result, submission_count))


@api.post("/surveys/<survey_id>/close")
@require_auth
def close_survey(survey_id):
    survey = owned_survey(survey_id)
    now = datetime.now(timezone.utc)
    result = db().surveys.find_one_and_update(
        {"_id": survey["_id"], "ownerId": g.current_user["_id"]},
        {
            "$set": {"status": "closed", "closedAt": now, "updatedAt": now},
            "$inc": {"version": 1},
        },
        return_document=True,
    )
    submission_count = db().submissions.count_documents(
        {"surveyId": survey["_id"]}
    )
    return ok(survey_summary(result, submission_count))


@api.get("/public/surveys/<slug>")
@require_auth
def public_survey(slug):
    survey = db().surveys.find_one({"slug": slug})
    if not survey:
        raise ApiError(404, "NOT_FOUND", "问卷不存在")
    now = datetime.now(timezone.utc)
    if (
        survey["status"] == "published"
        and survey.get("closesAt")
        and survey["closesAt"] <= now
    ):
        db().surveys.update_one(
            {"_id": survey["_id"], "status": "published"},
            {
                "$set": {
                    "status": "closed",
                    "closedAt": survey["closesAt"],
                    "updatedAt": now,
                }
            },
        )
        survey["status"] = "closed"
    if survey["status"] != "published":
        raise ApiError(
            410,
            "SURVEY_NOT_ACTIVE",
            "问卷尚未发布" if survey["status"] == "draft" else "问卷已关闭",
        )

    key = participant_key(survey["_id"], g.current_user["_id"])
    previous = None
    if not survey["allowMultipleResponses"]:
        previous = db().submissions.find_one(
            {"surveyId": survey["_id"], "participantKey": key},
            {"_id": 1},
        )
    return ok(
        {
            "id": str(survey["_id"]),
            "title": survey["title"],
            "description": survey["description"],
            "allowAnonymous": survey["allowAnonymous"],
            "allowMultipleResponses": survey["allowMultipleResponses"],
            "closesAt": survey.get("closesAt"),
            "canRespond": previous is None,
            "alreadySubmitted": previous is not None,
            "questions": [
                public_question(question)
                for question in questions_for_survey(survey["_id"])
            ],
        }
    )


@api.post("/public/surveys/<slug>/submit")
@require_auth
def submit_survey(slug):
    survey = db().surveys.find_one({"slug": slug})
    if not survey:
        raise ApiError(404, "NOT_FOUND", "问卷不存在")
    if survey["status"] != "published" or (
        survey.get("closesAt") and survey["closesAt"] <= datetime.now(timezone.utc)
    ):
        raise ApiError(410, "SURVEY_NOT_ACTIVE", "问卷已关闭或已截止")

    body = json_body()
    supplied_key = body.get("idempotencyKey")
    idempotency_key = (
        supplied_key
        if isinstance(supplied_key, str) and 10 <= len(supplied_key) <= 100
        else str(uuid.uuid4())
    )
    key = participant_key(survey["_id"], g.current_user["_id"])
    replay = db().submissions.find_one(
        {
            "surveyId": survey["_id"],
            "idempotencyKey": idempotency_key,
            "participantKey": key,
        }
    )
    if replay:
        return ok(
            {
                "submissionId": str(replay["_id"]),
                "submittedAt": replay["submittedAt"],
                "idempotentReplay": True,
            }
        )

    if not survey["allowMultipleResponses"] and db().submissions.find_one(
        {"surveyId": survey["_id"], "participantKey": key}
    ):
        raise ApiError(409, "ALREADY_SUBMITTED", "你已经填写过这份问卷")

    questions = questions_for_survey(survey["_id"])
    answers = evaluate_submission(questions, body.get("answers"))
    submission = {
        "surveyId": survey["_id"],
        "respondentId": None
        if survey["allowAnonymous"]
        else g.current_user["_id"],
        "participantKey": key,
        "anonymous": survey["allowAnonymous"],
        "enforceOnce": not survey["allowMultipleResponses"],
        "idempotencyKey": idempotency_key,
        "answers": answers,
        "submittedAt": datetime.now(timezone.utc),
    }
    try:
        inserted = db().submissions.insert_one(submission)
    except DuplicateKeyError:
        replay = db().submissions.find_one(
            {
                "surveyId": survey["_id"],
                "idempotencyKey": idempotency_key,
                "participantKey": key,
            }
        )
        if replay:
            return ok(
                {
                    "submissionId": str(replay["_id"]),
                    "submittedAt": replay["submittedAt"],
                    "idempotentReplay": True,
                }
            )
        raise ApiError(409, "ALREADY_SUBMITTED", "你已经填写过这份问卷") from None
    return ok(
        {
            "submissionId": str(inserted.inserted_id),
            "submittedAt": submission["submittedAt"],
        },
        201,
    )


@api.get("/surveys/<survey_id>/stats")
@require_auth
def survey_stats(survey_id):
    survey = owned_survey(survey_id)
    questions = questions_for_survey(survey["_id"])
    rows = list(
        db().submissions.aggregate(
            [
                {"$match": {"surveyId": survey["_id"]}},
                {
                    "$facet": {
                        "total": [{"$count": "count"}],
                        "answers": [
                            {"$unwind": "$answers"},
                            {
                                "$group": {
                                    "_id": "$answers.questionId",
                                    "values": {"$push": "$answers.value"},
                                }
                            },
                        ],
                    }
                },
            ]
        )
    )
    facet = rows[0] if rows else {"total": [], "answers": []}
    values_by_question = {
        row["_id"]: row["values"] for row in facet.get("answers", [])
    }
    statistics = []
    for question in questions:
        values = values_by_question.get(question["id"], [])
        item = {
            "id": question["id"],
            "title": question["title"],
            "type": question["type"],
            "order": question["order"],
            "answeredCount": len(values),
        }
        if question["type"] in {"single", "multiple"}:
            counts = {}
            for value in values:
                selected = value if isinstance(value, list) else [value]
                for option_id in selected:
                    counts[option_id] = counts.get(option_id, 0) + 1
            item["options"] = [
                {
                    **option,
                    "count": counts.get(option["id"], 0),
                    "percentage": round(
                        counts.get(option["id"], 0) * 100 / len(values),
                        1,
                    )
                    if values
                    else 0,
                }
                for option in question.get("options", [])
            ]
        elif question["type"] == "number":
            numbers = [
                value for value in values if isinstance(value, (int, float))
            ]
            item["numeric"] = {
                "average": round(sum(numbers) / len(numbers), 2)
                if numbers
                else None,
                "min": min(numbers) if numbers else None,
                "max": max(numbers) if numbers else None,
                "values": numbers,
            }
        else:
            item["textValues"] = values
        statistics.append(item)
    return ok(
        {
            "survey": survey_summary(survey),
            "totalSubmissions": (
                facet.get("total", [{}])[0].get("count", 0)
                if facet.get("total")
                else 0
            ),
            "generatedAt": datetime.now(timezone.utc),
            "questions": statistics,
        }
    )


@api.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_not_found(path):
    raise ApiError(404, "NOT_FOUND", "接口不存在")
