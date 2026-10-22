import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import MongoClient

from app.config import Config
from app.schema import initialize_database
from app.security import hash_password, username_key
from app.validation import normalize_questions


client = MongoClient(Config.MONGODB_URI, tz_aware=True)
db = client.get_default_database()
initialize_database(db)

demo_username = "demo"
demo_password = "Demo12345"
user = db.users.find_one({"usernameKey": username_key(demo_username)})
if user:
    old_surveys = list(db.surveys.find({"ownerId": user["_id"]}, {"_id": 1}))
    db.submissions.delete_many(
        {"surveyId": {"$in": [item["_id"] for item in old_surveys]}}
    )
    db.surveys.delete_many({"ownerId": user["_id"]})
    db.questions.delete_many(
        {"surveyId": {"$in": [item["_id"] for item in old_surveys]}}
    )
else:
    inserted = db.users.insert_one(
        {
            "username": demo_username,
            "usernameKey": username_key(demo_username),
            "passwordHash": hash_password(demo_password),
            "createdAt": datetime.now(timezone.utc),
        }
    )
    user = {"_id": inserted.inserted_id}

now = datetime.now(timezone.utc)
survey_id = ObjectId()
survey = {
    "_id": survey_id,
    "ownerId": user["_id"],
    "title": "产品体验小调查",
    "description": "约 1 分钟完成。跳转逻辑会根据你的选择展示不同题目。",
    "slug": secrets.token_urlsafe(9),
    "status": "published",
    "allowAnonymous": True,
    "allowMultipleResponses": True,
    "closesAt": now + timedelta(days=30),
    "publishedAt": now,
    "closedAt": None,
    "version": 1,
    "createdAt": now,
    "updatedAt": now,
}
db.surveys.insert_one(survey)

raw_questions = [
    {
        "id": "q_identity01",
        "type": "single",
        "title": "你目前的主要身份是？",
        "required": True,
        "options": [
            {"id": "o_student001", "label": "学生"},
            {"id": "o_worker0001", "label": "在职人员"},
        ],
        "jumps": [
            {
                "condition": {"optionId": "o_worker0001"},
                "targetQuestionId": "q_goal000001",
            }
        ],
    },
    {
        "id": "q_campus0001",
        "type": "text",
        "title": "你所在的学校或专业是？",
        "required": True,
        "validation": {"minLength": 2, "maxLength": 100},
    },
    {
        "id": "q_goal000001",
        "type": "multiple",
        "title": "你最关注哪些能力提升？",
        "required": True,
        "options": [
            {"id": "o_manage0001", "label": "时间管理"},
            {"id": "o_coding0001", "label": "编程实践"},
            {"id": "o_commu00001", "label": "沟通表达"},
            {"id": "o_career0001", "label": "求职准备"},
        ],
        "validation": {"minSelections": 1, "maxSelections": 2},
    },
    {
        "id": "q_age0000001",
        "type": "number",
        "title": "你的年龄是？",
        "required": True,
        "validation": {"min": 0, "max": 120, "integer": True},
        "jumps": [
            {
                "condition": {"operator": "gte", "value": 60},
                "targetQuestionId": "q_feedback01",
            }
        ],
    },
    {
        "id": "q_contact001",
        "type": "text",
        "title": "如果愿意接受回访，请留下联系方式（选填）",
        "required": False,
        "validation": {"minLength": 0, "maxLength": 100},
    },
    {
        "id": "q_feedback01",
        "type": "text",
        "title": "你对本产品的建议是什么？",
        "required": False,
        "validation": {"minLength": 0, "maxLength": 1000},
    },
]
questions = normalize_questions(raw_questions)
db.questions.insert_many(
    [
        {**question, "surveyId": survey_id, "createdAt": now}
        for question in questions
    ]
)

print(f"演示用户：{demo_username} / {demo_password}")
print(f"问卷链接：/survey/{survey['slug']}")
print(f"问卷 ID：{survey_id}")
