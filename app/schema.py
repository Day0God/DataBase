from pymongo.errors import CollectionInvalid


COLLECTION_VALIDATORS = {
    "users": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["username", "usernameKey", "passwordHash", "createdAt"],
            "properties": {
                "username": {"bsonType": "string"},
                "usernameKey": {"bsonType": "string"},
                "passwordHash": {"bsonType": "string"},
                "createdAt": {"bsonType": "date"},
            },
        }
    },
    "sessions": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["tokenHash", "userId", "createdAt", "expiresAt"],
            "properties": {
                "tokenHash": {"bsonType": "string"},
                "userId": {"bsonType": "objectId"},
                "createdAt": {"bsonType": "date"},
                "expiresAt": {"bsonType": "date"},
            },
        }
    },
    "surveys": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "ownerId",
                "title",
                "description",
                "slug",
                "status",
                "allowAnonymous",
                "allowMultipleResponses",
                "version",
                "createdAt",
                "updatedAt",
            ],
            "properties": {
                "ownerId": {"bsonType": "objectId"},
                "title": {"bsonType": "string"},
                "description": {"bsonType": "string"},
                "slug": {"bsonType": "string"},
                "status": {"enum": ["draft", "published", "closed"]},
                "allowAnonymous": {"bsonType": "bool"},
                "allowMultipleResponses": {"bsonType": "bool"},
                "closesAt": {"bsonType": ["date", "null"]},
                "publishedAt": {"bsonType": ["date", "null"]},
                "closedAt": {"bsonType": ["date", "null"]},
                "version": {
                    "bsonType": ["int", "long", "double"],
                    "minimum": 1,
                },
                "createdAt": {"bsonType": "date"},
                "updatedAt": {"bsonType": "date"},
            },
        }
    },
    "questions": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "surveyId",
                "id",
                "type",
                "title",
                "required",
                "order",
                "options",
                "validation",
                "jumps",
                "createdAt",
            ],
            "properties": {
                "surveyId": {"bsonType": "objectId"},
                "id": {"bsonType": "string"},
                "type": {"enum": ["single", "multiple", "text", "number"]},
                "title": {"bsonType": "string"},
                "required": {"bsonType": "bool"},
                "order": {
                    "bsonType": ["int", "long", "double"],
                    "minimum": 0,
                },
                "options": {"bsonType": "array"},
                "validation": {"bsonType": "object"},
                "jumps": {"bsonType": "array"},
                "createdAt": {"bsonType": "date"},
            },
        }
    },
    "submissions": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "surveyId",
                "respondentId",
                "participantKey",
                "anonymous",
                "enforceOnce",
                "answers",
                "submittedAt",
            ],
            "properties": {
                "surveyId": {"bsonType": "objectId"},
                "respondentId": {"bsonType": ["objectId", "null"]},
                "participantKey": {"bsonType": "string"},
                "anonymous": {"bsonType": "bool"},
                "enforceOnce": {"bsonType": "bool"},
                "idempotencyKey": {"bsonType": "string"},
                "answers": {"bsonType": "array"},
                "submittedAt": {"bsonType": "date"},
            },
        }
    },
}


def initialize_database(db):
    for name in COLLECTION_VALIDATORS:
        try:
            db.create_collection(name)
        except CollectionInvalid:
            pass

    for name, validator in COLLECTION_VALIDATORS.items():
        db.command(
            {
                "collMod": name,
                "validator": validator,
                "validationLevel": "strict",
                "validationAction": "error",
            }
        )

    db.users.create_index(
        [("usernameKey", 1)],
        unique=True,
        name="uk_users_username_key",
    )
    db.sessions.create_index(
        [("tokenHash", 1)],
        unique=True,
        name="uk_sessions_token_hash",
    )
    db.sessions.create_index(
        [("expiresAt", 1)],
        expireAfterSeconds=0,
        name="ttl_sessions_expires_at",
    )
    db.surveys.create_index(
        [("slug", 1)],
        unique=True,
        name="uk_surveys_slug",
    )
    db.surveys.create_index(
        [("ownerId", 1), ("createdAt", -1)],
        name="idx_surveys_owner_created",
    )
    db.surveys.create_index(
        [("status", 1), ("closesAt", 1)],
        name="idx_surveys_status_deadline",
    )
    db.questions.create_index(
        [("surveyId", 1), ("order", 1)],
        unique=True,
        name="uk_questions_survey_order",
    )
    db.submissions.create_index(
        [("surveyId", 1), ("submittedAt", -1)],
        name="idx_submissions_survey_time",
    )
    db.submissions.create_index(
        [("surveyId", 1), ("participantKey", 1)],
        unique=True,
        partialFilterExpression={"enforceOnce": True},
        name="uk_submissions_once",
    )
    db.submissions.create_index(
        [("surveyId", 1), ("idempotencyKey", 1)],
        unique=True,
        partialFilterExpression={"idempotencyKey": {"$type": "string"}},
        name="uk_submissions_idempotency",
    )
