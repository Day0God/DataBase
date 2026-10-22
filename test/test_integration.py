import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient

from app import create_app


QUESTIONS = [
    {
        "id": "q_route0001",
        "type": "single",
        "title": "选择调查路线",
        "required": True,
        "options": [
            {"id": "o_short0001", "label": "短路线"},
            {"id": "o_long00001", "label": "长路线"},
        ],
        "jumps": [
            {
                "condition": {"optionId": "o_short0001"},
                "targetQuestionId": "q_age000001",
            }
        ],
    },
    {
        "id": "q_reason001",
        "type": "text",
        "title": "短路线会跳过此题",
        "required": True,
        "validation": {"minLength": 2, "maxLength": 100},
    },
    {
        "id": "q_age000001",
        "type": "number",
        "title": "你的年龄",
        "required": True,
        "validation": {"min": 0, "max": 120, "integer": True},
        "jumps": [
            {
                "condition": {"operator": "gte", "value": 50},
                "targetQuestionId": "q_feedback1",
            }
        ],
    },
    {
        "id": "q_optional01",
        "type": "text",
        "title": "高龄路径跳过此题",
        "required": True,
        "validation": {"minLength": 1, "maxLength": 100},
    },
    {
        "id": "q_feedback1",
        "type": "text",
        "title": "补充反馈",
        "required": False,
        "validation": {"minLength": 0, "maxLength": 500},
    },
]


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = MongoClient(
            os.environ.get("TEST_MONGODB_URI", "mongodb://127.0.0.1:27018"),
            tz_aware=True,
            serverSelectionTimeoutMS=5000,
        )
        cls.database_name = f"dm_test_{uuid.uuid4().hex[:10]}"
        cls.db = cls.client[cls.database_name]
        cls.app = create_app(cls.db)
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        cls.client.drop_database(cls.database_name)
        cls.client.close()

    def setUp(self):
        self.db.users.delete_many({})
        self.db.sessions.delete_many({})
        self.db.surveys.delete_many({})
        self.db.questions.delete_many({})
        self.db.submissions.delete_many({})
        self.owner = self.app.test_client()
        self.respondent = self.app.test_client()

    def post(self, client, path, payload=None):
        return client.post(
            path,
            json=payload if payload is not None else {},
            content_type="application/json",
        )

    def patch(self, client, path, payload):
        return client.patch(path, json=payload, content_type="application/json")

    def put(self, client, path, payload):
        return client.put(path, json=payload, content_type="application/json")

    def register(self, client, username):
        return self.post(
            client,
            "/api/auth/register",
            {"username": username, "password": "Password123"},
        )

    def create_published_survey(self, allow_anonymous=True):
        self.assertEqual(self.register(self.owner, "owner_user").status_code, 201)
        response = self.post(
            self.owner,
            "/api/surveys",
            {
                "title": "端到端测试问卷",
                "description": "验证跳转、校验与统计",
                "allowAnonymous": allow_anonymous,
                "allowMultipleResponses": False,
                "closesAt": (
                    datetime.now(timezone.utc) + timedelta(days=2)
                ).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        survey = response.get_json()["data"]
        response = self.put(
            self.owner,
            f"/api/surveys/{survey['id']}/questions",
            {"questions": QUESTIONS},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        response = self.post(
            self.owner,
            f"/api/surveys/{survey['id']}/publish",
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return survey

    def test_authentication_validation_and_owner_isolation(self):
        response = self.register(self.owner, "owner_user")
        self.assertEqual(response.status_code, 201)
        self.assertIn("dm_session=", response.headers.get("Set-Cookie", ""))
        registered_user = response.get_json()["data"]["user"]
        self.assertNotIn("passwordHash", registered_user)
        self.assertTrue(registered_user["createdAt"])

        duplicate = self.register(self.respondent, "owner_user")
        self.assertEqual(duplicate.status_code, 409)

        survey = self.post(
            self.owner,
            "/api/surveys",
            {
                "title": "私有问卷",
                "description": "",
                "allowAnonymous": False,
                "allowMultipleResponses": False,
            },
        ).get_json()["data"]
        self.register(self.respondent, "other_user")
        forbidden = self.respondent.get(f"/api/surveys/{survey['id']}")
        self.assertEqual(forbidden.status_code, 404)

    def test_create_survey_and_add_questions_api(self):
        self.assertEqual(self.register(self.owner, "survey_creator").status_code, 201)
        created = self.post(
            self.owner,
            "/api/surveys",
            {
                "title": "创建与加题测试",
                "description": "验证问卷初始状态和题目写入",
                "allowAnonymous": True,
                "allowMultipleResponses": False,
            },
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        survey = created.get_json()["data"]
        self.assertEqual(survey["status"], "draft")
        self.assertEqual(survey["submissionCount"], 0)
        self.assertFalse(survey["hasResponses"])

        added = self.put(
            self.owner,
            f"/api/surveys/{survey['id']}/questions",
            {"questions": QUESTIONS},
        )
        self.assertEqual(added.status_code, 200, added.get_json())
        questions = added.get_json()["data"]
        self.assertEqual(len(questions), 5)
        self.assertEqual([item["order"] for item in questions], list(range(5)))
        self.assertEqual(questions[0]["type"], "single")
        self.assertEqual(questions[2]["type"], "number")

    def test_full_survey_flow_jump_submission_idempotency_and_stats(self):
        survey = self.create_published_survey()
        self.assertEqual(self.register(self.respondent, "respondent").status_code, 201)

        public_response = self.respondent.get(
            f"/api/public/surveys/{survey['slug']}"
        )
        self.assertEqual(public_response.status_code, 200)
        public_data = public_response.get_json()["data"]
        self.assertTrue(public_data["canRespond"])
        self.assertEqual(len(public_data["questions"]), 5)

        invalid = self.post(
            self.respondent,
            f"/api/public/surveys/{survey['slug']}/submit",
            {
                "answers": [
                    {"questionId": "q_route0001", "value": "o_short0001"},
                    {"questionId": "q_age000001", "value": 20.5},
                ]
            },
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.get_json()["error"]["code"], "VALIDATION_ERROR")

        skipped_answer = self.post(
            self.respondent,
            f"/api/public/surveys/{survey['slug']}/submit",
            {
                "answers": [
                    {"questionId": "q_route0001", "value": "o_short0001"},
                    {"questionId": "q_age000001", "value": 60},
                    {"questionId": "q_reason001", "value": "不应提交"},
                    {"questionId": "q_feedback1", "value": "很好"},
                ]
            },
        )
        self.assertEqual(skipped_answer.status_code, 422)
        self.assertEqual(
            skipped_answer.get_json()["error"]["code"],
            "UNEXPECTED_ANSWER",
        )

        payload = {
            "idempotencyKey": "browser-submit-key-0001",
            "answers": [
                {"questionId": "q_route0001", "value": "o_short0001"},
                {"questionId": "q_age000001", "value": 60},
                {"questionId": "q_feedback1", "value": "界面清晰，跳转自然"},
            ],
        }
        submitted = self.post(
            self.respondent,
            f"/api/public/surveys/{survey['slug']}/submit",
            payload,
        )
        self.assertEqual(submitted.status_code, 201, submitted.get_json())
        submission_id = submitted.get_json()["data"]["submissionId"]
        stored = self.db.submissions.find_one({})
        self.assertTrue(stored["anonymous"])
        self.assertIsNone(stored["respondentId"])
        self.assertEqual(
            [answer["questionId"] for answer in stored["answers"]],
            ["q_route0001", "q_age000001", "q_feedback1"],
        )

        replay = self.post(
            self.respondent,
            f"/api/public/surveys/{survey['slug']}/submit",
            payload,
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.get_json()["data"]["idempotentReplay"])
        self.assertEqual(
            replay.get_json()["data"]["submissionId"],
            submission_id,
        )

        duplicate = self.post(
            self.respondent,
            f"/api/public/surveys/{survey['slug']}/submit",
            {
                "idempotencyKey": "browser-submit-key-0002",
                "answers": payload["answers"],
            },
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.get_json()["error"]["code"], "ALREADY_SUBMITTED")

        stats = self.owner.get(f"/api/surveys/{survey['id']}/stats")
        self.assertEqual(stats.status_code, 200)
        stats_data = stats.get_json()["data"]
        self.assertEqual(stats_data["totalSubmissions"], 1)
        by_id = {item["id"]: item for item in stats_data["questions"]}
        self.assertEqual(by_id["q_route0001"]["options"][0]["count"], 1)
        self.assertEqual(by_id["q_age000001"]["numeric"]["average"], 60)
        self.assertEqual(by_id["q_reason001"]["answeredCount"], 0)
        self.assertEqual(by_id["q_feedback1"]["textValues"], ["界面清晰，跳转自然"])

    def test_published_survey_questions_cannot_be_modified(self):
        survey = self.create_published_survey()
        response = self.put(
            self.owner,
            f"/api/surveys/{survey['id']}/questions",
            {"questions": QUESTIONS},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["code"], "SURVEY_PUBLISHED")

    def test_closed_survey_with_answers_can_be_republished(self):
        survey = self.create_published_survey()
        self.assertEqual(self.register(self.respondent, "respondent").status_code, 201)
        submitted = self.post(
            self.respondent,
            f"/api/public/surveys/{survey['slug']}/submit",
            {
                "idempotencyKey": "close-and-republish-0001",
                "answers": [
                    {"questionId": "q_route0001", "value": "o_short0001"},
                    {"questionId": "q_age000001", "value": 20},
                    {"questionId": "q_optional01", "value": "继续填写"},
                ],
            },
        )
        self.assertEqual(submitted.status_code, 201, submitted.get_json())

        closed = self.post(self.owner, f"/api/surveys/{survey['id']}/close")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.get_json()["data"]["status"], "closed")
        self.assertEqual(closed.get_json()["data"]["submissionCount"], 1)
        self.assertTrue(closed.get_json()["data"]["hasResponses"])

        detail = self.owner.get(f"/api/surveys/{survey['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.get_json()["data"]["survey"]["hasResponses"])

        locked_questions = self.put(
            self.owner,
            f"/api/surveys/{survey['id']}/questions",
            {"questions": QUESTIONS},
        )
        self.assertEqual(locked_questions.status_code, 409)
        self.assertEqual(
            locked_questions.get_json()["error"]["code"],
            "SURVEY_HAS_RESPONSES",
        )

        reopened = self.post(
            self.owner,
            f"/api/surveys/{survey['id']}/publish",
        )
        self.assertEqual(reopened.status_code, 200, reopened.get_json())
        self.assertEqual(reopened.get_json()["data"]["status"], "published")
        self.assertEqual(reopened.get_json()["data"]["submissionCount"], 1)
        self.assertTrue(reopened.get_json()["data"]["hasResponses"])

    def test_public_survey_requires_login(self):
        survey = self.create_published_survey()
        anonymous_client = self.app.test_client()
        response = anonymous_client.get(f"/api/public/surveys/{survey['slug']}")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
