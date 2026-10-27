import math
import re
import secrets
import unicodedata
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
    new_question_id,
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
    result = {
        "id": question["id"],
        "type": question["type"],
        "title": question["title"],
        "required": question["required"],
        "order": question["order"],
        "options": question.get("options", []),
        "validation": question.get("validation", {}),
        "jumps": question.get("jumps", []),
    }
    if question.get("libraryQuestionId"):
        result.update(
            {
                "libraryQuestionId": str(question["libraryQuestionId"]),
                "libraryVersionId": str(question["libraryVersionId"]),
                "libraryVersionNumber": question["libraryVersionNumber"],
            }
        )
    return result


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


def library_name_key(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def normalize_library_snapshot(raw_question):
    raw_question = raw_question if isinstance(raw_question, dict) else {}
    candidate = {
        **raw_question,
        "id": new_question_id(),
        "order": 0,
        "jumps": [],
    }
    normalized = normalize_questions([candidate])[0]
    return {
        "title": normalized["title"],
        "type": normalized["type"],
        "required": normalized["required"],
        "options": normalized["options"],
        "validation": normalized["validation"],
    }


def library_version_public(version):
    return {
        "id": str(version["_id"]),
        "versionNumber": version["versionNumber"],
        "parentVersionId": (
            str(version["parentVersionId"])
            if version.get("parentVersionId")
            else None
        ),
        "restoredFromVersionId": (
            str(version["restoredFromVersionId"])
            if version.get("restoredFromVersionId")
            else None
        ),
        "snapshot": version["snapshot"],
        "changeSummary": version.get("changeSummary", ""),
        "createdAt": version["createdAt"],
    }


def library_question_for_access(question_id_input, owner_only=False):
    question_id = object_id(question_id_input, "题库题目")
    question = db().library_questions.find_one(
        {
            "_id": question_id,
            "$or": [
                {"ownerId": g.current_user["_id"]},
                {"sharedWith": g.current_user["_id"]},
            ],
        }
    )
    if not question:
        raise ApiError(404, "NOT_FOUND", "题库题目不存在")
    if owner_only and question["ownerId"] != g.current_user["_id"]:
        raise ApiError(403, "FORBIDDEN", "只有题目所有者可以执行此操作")
    return question


def library_question_summary(question):
    version = db().library_question_versions.find_one(
        {"_id": question["currentVersionId"]}
    )
    if not version:
        raise ApiError(500, "INVALID_LIBRARY_STATE", "题目版本数据不完整")
    bank = db().question_banks.find_one({"_id": question["bankId"]})
    owner = db().users.find_one({"_id": question["ownerId"]}, {"username": 1})
    is_owner = question["ownerId"] == g.current_user["_id"]
    return {
        "id": str(question["_id"]),
        "bankId": str(question["bankId"]),
        "bankName": bank["name"] if bank else "已删除题库",
        "ownerId": str(question["ownerId"]),
        "ownerUsername": owner["username"] if owner else "未知用户",
        "isOwner": is_owner,
        "isShared": not is_owner,
        "canEdit": is_owner,
        "sharedWithCount": len(question.get("sharedWith", [])),
        "currentVersion": library_version_public(version),
        "createdAt": question["createdAt"],
        "updatedAt": question["updatedAt"],
    }


def attach_library_references(normalized_questions, raw_questions):
    if not isinstance(raw_questions, list):
        return
    for question, raw_question in zip(normalized_questions, raw_questions):
        raw_question = raw_question if isinstance(raw_question, dict) else {}
        library_id = raw_question.get("libraryQuestionId")
        version_id = raw_question.get("libraryVersionId")
        if not library_id or not version_id:
            continue
        try:
            library_question = library_question_for_access(
                library_id,
                owner_only=False,
            )
            version = db().library_question_versions.find_one(
                {
                    "_id": ObjectId(version_id),
                    "questionId": library_question["_id"],
                }
            )
        except (ApiError, InvalidId, TypeError):
            continue
        if not version:
            continue
        snapshot = version["snapshot"]
        unchanged = all(
            question.get(field) == snapshot.get(field)
            for field in ("title", "type", "required", "options", "validation")
        )
        if not unchanged:
            continue
        question.update(
            {
                "libraryQuestionId": library_question["_id"],
                "libraryVersionId": version["_id"],
                "libraryVersionNumber": version["versionNumber"],
                "libraryOwnerId": library_question["ownerId"],
            }
        )


def accessible_bank(bank_id_input):
    bank_id = object_id(bank_id_input, "题库")
    bank = db().question_banks.find_one(
        {"_id": bank_id, "ownerId": g.current_user["_id"]}
    )
    if not bank:
        raise ApiError(404, "NOT_FOUND", "题库不存在")
    return bank


def ensure_default_bank():
    existing = db().question_banks.find_one(
        {"ownerId": g.current_user["_id"]},
        sort=[("createdAt", 1)],
    )
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    bank = {
        "ownerId": g.current_user["_id"],
        "name": "我的题库",
        "nameKey": library_name_key("我的题库"),
        "description": "用于保存可复用的问卷题目",
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        inserted = db().question_banks.insert_one(bank)
    except DuplicateKeyError:
        return db().question_banks.find_one(
            {"ownerId": g.current_user["_id"]},
            sort=[("createdAt", 1)],
        )
    bank["_id"] = inserted.inserted_id
    return bank


def bank_public(bank):
    return {
        "id": str(bank["_id"]),
        "name": bank["name"],
        "description": bank["description"],
        "questionCount": db().library_questions.count_documents(
            {"bankId": bank["_id"], "ownerId": g.current_user["_id"]}
        ),
        "createdAt": bank["createdAt"],
        "updatedAt": bank["updatedAt"],
    }


def question_values(question_documents):
    if not question_documents:
        return [], 0
    question_ids = [question["id"] for question in question_documents]
    survey_ids = list(
        {question["surveyId"] for question in question_documents}
    )
    match = {
        "surveyId": {"$in": survey_ids},
        "answers.questionId": {"$in": question_ids},
    }
    rows = list(
        db().submissions.aggregate(
            [
                {"$match": match},
                {"$unwind": "$answers"},
                {"$match": {"answers.questionId": {"$in": question_ids}}},
                {
                    "$group": {
                        "_id": None,
                        "values": {"$push": "$answers.value"},
                        "submissionIds": {"$addToSet": "$_id"},
                    }
                },
            ]
        )
    )
    if not rows:
        return [], 0
    return rows[0]["values"], len(rows[0]["submissionIds"])


def summarize_question_values(snapshot, values):
    result = {
        "type": snapshot["type"],
        "answeredCount": len(values),
    }
    if snapshot["type"] in {"single", "multiple"}:
        counts = {}
        for value in values:
            selected = value if isinstance(value, list) else [value]
            for option_id in selected:
                counts[option_id] = counts.get(option_id, 0) + 1
        result["options"] = [
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
            for option in snapshot.get("options", [])
        ]
    elif snapshot["type"] == "number":
        numbers = [
            value for value in values if isinstance(value, (int, float))
        ]
        result["numeric"] = {
            "average": round(sum(numbers) / len(numbers), 2)
            if numbers
            else None,
            "min": min(numbers) if numbers else None,
            "max": max(numbers) if numbers else None,
            "values": numbers,
        }
    else:
        result["textValues"] = values
    return result


def statistics_snapshot(current_snapshot, question_documents):
    if current_snapshot["type"] not in {"single", "multiple"}:
        return current_snapshot
    options = {}
    for option in current_snapshot.get("options", []):
        options[option["id"]] = option
    for document in question_documents:
        for option in document.get("options", []):
            options.setdefault(option["id"], option)
    return {**current_snapshot, "options": list(options.values())}


@api.get("/question-banks")
@require_auth
def list_question_banks():
    ensure_default_bank()
    banks = list(
        db().question_banks.find(
            {"ownerId": g.current_user["_id"]}
        ).sort("createdAt", 1)
    )
    return ok([bank_public(bank) for bank in banks])


@api.post("/question-banks")
@require_auth
def create_question_bank():
    data = json_body()
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    ensure(
        1 <= len(name) <= 60,
        422,
        "VALIDATION_ERROR",
        "题库名称应为 1 到 60 个字符",
    )
    ensure(
        len(description) <= 500,
        422,
        "VALIDATION_ERROR",
        "题库说明不能超过 500 个字符",
    )
    now = datetime.now(timezone.utc)
    bank = {
        "ownerId": g.current_user["_id"],
        "name": name,
        "nameKey": library_name_key(name),
        "description": description,
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        inserted = db().question_banks.insert_one(bank)
    except DuplicateKeyError:
        raise ApiError(409, "BANK_NAME_TAKEN", "同名题库已存在") from None
    bank["_id"] = inserted.inserted_id
    return ok(bank_public(bank), 201)


@api.patch("/question-banks/<bank_id>")
@require_auth
def update_question_bank(bank_id):
    bank = accessible_bank(bank_id)
    data = json_body()
    fields = {}
    if "name" in data:
        name = str(data.get("name", "")).strip()
        ensure(
            1 <= len(name) <= 60,
            422,
            "VALIDATION_ERROR",
            "题库名称应为 1 到 60 个字符",
        )
        fields.update({"name": name, "nameKey": library_name_key(name)})
    if "description" in data:
        description = str(data.get("description", "")).strip()
        ensure(
            len(description) <= 500,
            422,
            "VALIDATION_ERROR",
            "题库说明不能超过 500 个字符",
        )
        fields["description"] = description
    ensure(fields, 422, "VALIDATION_ERROR", "没有可更新的字段")
    fields["updatedAt"] = datetime.now(timezone.utc)
    try:
        updated = db().question_banks.find_one_and_update(
            {"_id": bank["_id"], "ownerId": g.current_user["_id"]},
            {"$set": fields},
            return_document=True,
        )
    except DuplicateKeyError:
        raise ApiError(409, "BANK_NAME_TAKEN", "同名题库已存在") from None
    return ok(bank_public(updated))


@api.get("/library-questions")
@require_auth
def list_library_questions():
    scope = request.args.get("scope", "all")
    ensure(
        scope in {"all", "own", "shared"},
        422,
        "VALIDATION_ERROR",
        "题库范围无效",
    )
    if scope == "own":
        access_query = {"ownerId": g.current_user["_id"]}
    elif scope == "shared":
        access_query = {"sharedWith": g.current_user["_id"]}
    else:
        access_query = {
            "$or": [
                {"ownerId": g.current_user["_id"]},
                {"sharedWith": g.current_user["_id"]},
            ]
        }
    query = access_query
    bank_id = request.args.get("bankId")
    if bank_id:
        query = {
            "$and": [
                access_query,
                {"bankId": object_id(bank_id, "题库")},
            ]
        }
    questions = list(
        db().library_questions.find(query).sort("updatedAt", -1)
    )
    return ok([library_question_summary(question) for question in questions])


@api.post("/library-questions")
@require_auth
def create_library_question():
    data = json_body()
    bank_id = data.get("bankId")
    bank = accessible_bank(bank_id) if bank_id else ensure_default_bank()
    snapshot = normalize_library_snapshot(data.get("question", data))
    now = datetime.now(timezone.utc)
    question_id = ObjectId()
    version_id = ObjectId()
    version = {
        "_id": version_id,
        "questionId": question_id,
        "versionNumber": 1,
        "parentVersionId": None,
        "restoredFromVersionId": None,
        "snapshot": snapshot,
        "changeSummary": (
            str(data.get("changeSummary", "")).strip() or "创建题目"
        )[:300],
        "createdBy": g.current_user["_id"],
        "createdAt": now,
    }
    db().library_question_versions.insert_one(version)
    question = {
        "_id": question_id,
        "bankId": bank["_id"],
        "ownerId": g.current_user["_id"],
        "type": snapshot["type"],
        "currentVersionId": version_id,
        "currentVersionNumber": 1,
        "sharedWith": [],
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        db().library_questions.insert_one(question)
    except Exception:
        db().library_question_versions.delete_one({"_id": version_id})
        raise
    return ok(library_question_summary(question), 201)


@api.get("/library-questions/<question_id>")
@require_auth
def get_library_question(question_id):
    question = library_question_for_access(question_id)
    versions = list(
        db().library_question_versions.find(
            {"questionId": question["_id"]}
        ).sort("versionNumber", 1)
    )
    return ok(
        {
            "question": library_question_summary(question),
            "versions": [
                library_version_public(version) for version in versions
            ],
        }
    )


@api.post("/library-questions/<question_id>/versions")
@require_auth
def create_library_question_version(question_id):
    question = library_question_for_access(question_id, owner_only=True)
    data = json_body()
    base_version_id = data.get("baseVersionId") or question["currentVersionId"]
    base_version = db().library_question_versions.find_one(
        {
            "_id": object_id(base_version_id, "题目版本"),
            "questionId": question["_id"],
        }
    )
    if not base_version:
        raise ApiError(404, "NOT_FOUND", "题目版本不存在")
    candidate = data.get("snapshot") or data.get("question") or base_version[
        "snapshot"
    ]
    snapshot = normalize_library_snapshot(candidate)
    ensure(
        snapshot["type"] == question["type"],
        422,
        "LIBRARY_TYPE_IMMUTABLE",
        "同一题目的历史版本不能改变题型",
    )
    now = datetime.now(timezone.utc)
    current = db().library_questions.find_one({"_id": question["_id"]})
    next_number = int(current["currentVersionNumber"]) + 1
    version_id = ObjectId()
    version = {
        "_id": version_id,
        "questionId": question["_id"],
        "versionNumber": next_number,
        "parentVersionId": base_version["_id"],
        "restoredFromVersionId": None,
        "snapshot": snapshot,
        "changeSummary": (
            str(data.get("changeSummary", "")).strip()
            or f"基于 v{base_version['versionNumber']} 创建新版本"
        )[:300],
        "createdBy": g.current_user["_id"],
        "createdAt": now,
    }
    try:
        db().library_question_versions.insert_one(version)
    except DuplicateKeyError:
        raise ApiError(
            409,
            "LIBRARY_VERSION_CONFLICT",
            "题目版本已被其他操作更新，请刷新后重试",
        ) from None
    result = db().library_questions.update_one(
        {
            "_id": question["_id"],
            "ownerId": g.current_user["_id"],
            "currentVersionId": current["currentVersionId"],
        },
        {
            "$set": {
                "currentVersionId": version_id,
                "currentVersionNumber": next_number,
                "updatedAt": now,
            }
        },
    )
    if result.modified_count != 1:
        db().library_question_versions.delete_one({"_id": version_id})
        raise ApiError(
            409,
            "LIBRARY_VERSION_CONFLICT",
            "题目版本已被其他操作更新，请刷新后重试",
        )
    question["currentVersionId"] = version_id
    question["currentVersionNumber"] = next_number
    question["updatedAt"] = now
    return ok(library_question_summary(question), 201)


@api.post("/library-questions/<question_id>/restore")
@require_auth
def restore_library_question_version(question_id):
    question = library_question_for_access(question_id, owner_only=True)
    data = json_body()
    source_version = db().library_question_versions.find_one(
        {
            "_id": object_id(data.get("versionId"), "题目版本"),
            "questionId": question["_id"],
        }
    )
    if not source_version:
        raise ApiError(404, "NOT_FOUND", "要恢复的题目版本不存在")
    now = datetime.now(timezone.utc)
    next_number = int(question["currentVersionNumber"]) + 1
    version_id = ObjectId()
    version = {
        "_id": version_id,
        "questionId": question["_id"],
        "versionNumber": next_number,
        "parentVersionId": question["currentVersionId"],
        "restoredFromVersionId": source_version["_id"],
        "snapshot": source_version["snapshot"],
        "changeSummary": (
            str(data.get("changeSummary", "")).strip()
            or f"恢复自 v{source_version['versionNumber']}"
        )[:300],
        "createdBy": g.current_user["_id"],
        "createdAt": now,
    }
    try:
        db().library_question_versions.insert_one(version)
    except DuplicateKeyError:
        raise ApiError(
            409,
            "LIBRARY_VERSION_CONFLICT",
            "题目版本已被其他操作更新，请刷新后重试",
        ) from None
    result = db().library_questions.update_one(
        {
            "_id": question["_id"],
            "currentVersionId": question["currentVersionId"],
        },
        {
            "$set": {
                "currentVersionId": version_id,
                "currentVersionNumber": next_number,
                "updatedAt": now,
            }
        },
    )
    if result.modified_count != 1:
        db().library_question_versions.delete_one({"_id": version_id})
        raise ApiError(
            409,
            "LIBRARY_VERSION_CONFLICT",
            "题目版本已被其他操作更新，请刷新后重试",
        )
    question["currentVersionId"] = version_id
    question["currentVersionNumber"] = next_number
    question["updatedAt"] = now
    return ok(library_question_summary(question), 201)


@api.post("/library-questions/<question_id>/share")
@require_auth
def share_library_question(question_id):
    question = library_question_for_access(question_id, owner_only=True)
    username = str(json_body().get("username", "")).strip()
    recipient = db().users.find_one({"usernameKey": username_key(username)})
    if not recipient:
        raise ApiError(404, "NOT_FOUND", "要共享的用户不存在")
    if recipient["_id"] == g.current_user["_id"]:
        raise ApiError(422, "VALIDATION_ERROR", "不能共享给自己")
    now = datetime.now(timezone.utc)
    db().library_questions.update_one(
        {"_id": question["_id"], "ownerId": g.current_user["_id"]},
        {
            "$addToSet": {"sharedWith": recipient["_id"]},
            "$set": {"updatedAt": now},
        },
    )
    return ok(
        {
            "questionId": str(question["_id"]),
            "recipient": public_user(recipient),
        }
    )


@api.delete("/library-questions/<question_id>/share/<user_id>")
@require_auth
def unshare_library_question(question_id, user_id):
    question = library_question_for_access(question_id, owner_only=True)
    recipient_id = object_id(user_id, "用户")
    db().library_questions.update_one(
        {"_id": question["_id"], "ownerId": g.current_user["_id"]},
        {
            "$pull": {"sharedWith": recipient_id},
            "$set": {"updatedAt": datetime.now(timezone.utc)},
        },
    )
    return ok({"questionId": str(question["_id"]), "removed": True})


@api.get("/library-questions/<question_id>/usages")
@require_auth
def library_question_usages(question_id):
    question = library_question_for_access(question_id)
    is_owner = question["ownerId"] == g.current_user["_id"]
    survey_filter = {} if is_owner else {"ownerId": g.current_user["_id"]}
    survey_ids = [row["_id"] for row in db().surveys.find(survey_filter, {"_id": 1})]
    usages = []
    if survey_ids:
        documents = list(
            db().questions.find(
                {
                    "libraryQuestionId": question["_id"],
                    "surveyId": {"$in": survey_ids},
                }
            ).sort("surveyId", 1)
        )
        surveys = {
            survey["_id"]: survey
            for survey in db().surveys.find(
                {"_id": {"$in": list({item["surveyId"] for item in documents})}}
            )
        }
        usages = [
            {
                "surveyId": str(document["surveyId"]),
                "surveyTitle": surveys[document["surveyId"]]["title"],
                "surveyStatus": surveys[document["surveyId"]]["status"],
                "questionId": document["id"],
                "libraryVersionId": (
                    str(document["libraryVersionId"])
                    if document.get("libraryVersionId")
                    else None
                ),
                "libraryVersionNumber": document.get(
                    "libraryVersionNumber"
                ),
            }
            for document in documents
            if document["surveyId"] in surveys
        ]
    return ok(
        {
            "questionId": str(question["_id"]),
            "totalUsages": len(usages),
            "scope": (
                "题目所有者可查看全部使用位置"
                if is_owner
                else "共享用户仅查看自己拥有的问卷"
            ),
            "usages": usages,
        }
    )


@api.get("/library-questions/<question_id>/stats")
@require_auth
def library_question_stats(question_id):
    question = library_question_for_access(question_id)
    survey_ids = [
        row["_id"]
        for row in db().surveys.find(
            {"ownerId": g.current_user["_id"]}, {"_id": 1}
        )
    ]
    version_value = request.args.get("versionId")
    version_id = (
        object_id(version_value, "题目版本") if version_value else None
    )
    documents = []
    if survey_ids:
        documents = list(
            db().questions.find(
                {
                    "libraryQuestionId": question["_id"],
                    "surveyId": {"$in": survey_ids},
                    **(
                        {"libraryVersionId": version_id}
                        if version_id is not None
                        else {}
                    ),
                }
            )
        )
    current = db().library_question_versions.find_one(
        {"_id": question["currentVersionId"]}
    )
    values, total_submissions = question_values(documents)
    summary = summarize_question_values(
        statistics_snapshot(current["snapshot"], documents),
        values,
    )
    summary.update(
        {
            "question": library_question_summary(question),
            "versionFilter": (
                str(version_id) if version_id is not None else "all"
            ),
            "versionsIncluded": sorted(
                {
                    int(document["libraryVersionNumber"])
                    for document in documents
                    if document.get("libraryVersionNumber")
                }
            ),
            "surveyUsageCount": len(
                {document["surveyId"] for document in documents}
            ),
            "totalSubmissions": total_submissions,
            "scope": "仅汇总当前用户拥有的问卷",
            "generatedAt": datetime.now(timezone.utc),
        }
    )
    return ok(summary)


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
    raw_questions = json_body().get("questions")
    questions = normalize_questions(raw_questions)
    attach_library_references(questions, raw_questions)
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
