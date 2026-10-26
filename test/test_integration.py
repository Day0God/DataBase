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
        self.db.question_banks.delete_many({})
        self.db.library_questions.delete_many({})
        self.db.library_question_versions.delete_many({})
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

    def create_library_number_question(self, title="你的年龄"):
        banks = self.owner.get("/api/question-banks")
        self.assertEqual(banks.status_code, 200, banks.get_json())
        bank = banks.get_json()["data"][0]
        response = self.post(
            self.owner,
            "/api/library-questions",
            {
                "bankId": bank["id"],
                "question": {
                    "type": "number",
                    "title": title,
                    "required": True,
                    "validation": {"min": 0, "max": 120, "integer": True},
                },
                "changeSummary": "创建共用年龄题",
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["data"]

    def create_survey_with_library_question(
        self,
        client,
        title,
        library_question,
        survey_question_id,
    ):
        created = self.post(
            client,
            "/api/surveys",
            {
                "title": title,
                "description": "使用题库题目",
                "allowAnonymous": True,
                "allowMultipleResponses": False,
            },
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        survey = created.get_json()["data"]
        snapshot = library_question["currentVersion"]["snapshot"]
        version = library_question["currentVersion"]
        question = {
            **snapshot,
            "id": survey_question_id,
            "order": 0,
            "jumps": [],
            "libraryQuestionId": library_question["id"],
            "libraryVersionId": version["id"],
            "libraryVersionNumber": version["versionNumber"],
        }
        saved = self.put(
            client,
            f"/api/surveys/{survey['id']}/questions",
            {"questions": [question]},
        )
        self.assertEqual(saved.status_code, 200, saved.get_json())
        published = self.post(
            client,
            f"/api/surveys/{survey['id']}/publish",
        )
        self.assertEqual(published.status_code, 200, published.get_json())
        return survey, saved.get_json()["data"][0]

    def test_library_question_sharing_and_version_permissions(self):
        self.assertEqual(self.register(self.owner, "library_owner").status_code, 201)
        library = self.create_library_number_question()
        self.assertEqual(library["currentVersion"]["versionNumber"], 1)

        colleague = self.app.test_client()
        self.assertEqual(self.register(colleague, "colleague").status_code, 201)
        self.assertEqual(
            colleague.get("/api/library-questions?scope=shared")
            .get_json()["data"],
            [],
        )
        shared = self.post(
            self.owner,
            f"/api/library-questions/{library['id']}/share",
            {"username": "colleague"},
        )
        self.assertEqual(shared.status_code, 200, shared.get_json())

        shared_list = colleague.get("/api/library-questions?scope=shared")
        self.assertEqual(shared_list.status_code, 200)
        shared_question = shared_list.get_json()["data"][0]
        self.assertEqual(shared_question["id"], library["id"])
        self.assertFalse(shared_question["canEdit"])
        self.assertTrue(shared_question["isShared"])
        library_page = colleague.get("/library")
        self.assertEqual(library_page.status_code, 200)
        self.assertIn(b"/js/library.js", library_page.data)
        library_page.close()

        denied = self.post(
            colleague,
            f"/api/library-questions/{library['id']}/versions",
            {"changeSummary": "不应成功"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            denied.get_json()["error"]["code"],
            "FORBIDDEN",
        )
        shared_survey, shared_snapshot = self.create_survey_with_library_question(
            colleague,
            "同事使用共享题目",
            shared_question,
            "q_shared0001",
        )
        self.assertEqual(
            shared_snapshot["libraryQuestionId"],
            library["id"],
        )
        detail = colleague.get(f"/api/surveys/{shared_survey['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.get_json()["data"]["questions"][0]["libraryVersionNumber"],
            1,
        )

    def test_library_versions_preserve_survey_snapshots_and_lineage(self):
        self.assertEqual(self.register(self.owner, "version_owner").status_code, 201)
        library = self.create_library_number_question("年龄原题")
        first_survey, first_question = self.create_survey_with_library_question(
            self.owner,
            "旧版问卷",
            library,
            "q_library001",
        )
        self.assertEqual(first_question["libraryVersionNumber"], 1)

        snapshot_v2 = {
            **library["currentVersion"]["snapshot"],
            "title": "年龄新版",
            "validation": {"min": 18, "max": 120, "integer": True},
        }
        version_response = self.post(
            self.owner,
            f"/api/library-questions/{library['id']}/versions",
            {
                "baseVersionId": library["currentVersion"]["id"],
                "snapshot": snapshot_v2,
                "changeSummary": "限制为成年人",
            },
        )
        self.assertEqual(version_response.status_code, 201)
        library_v2 = version_response.get_json()["data"]
        self.assertEqual(library_v2["currentVersion"]["versionNumber"], 2)
        self.assertEqual(
            library_v2["currentVersion"]["parentVersionId"],
            library["currentVersion"]["id"],
        )

        second_survey, second_question = self.create_survey_with_library_question(
            self.owner,
            "新版问卷",
            library_v2,
            "q_library002",
        )
        self.assertEqual(second_question["libraryVersionNumber"], 2)

        first_detail = self.owner.get(f"/api/surveys/{first_survey['id']}")
        self.assertEqual(first_detail.status_code, 200)
        old_question = first_detail.get_json()["data"]["questions"][0]
        self.assertEqual(old_question["title"], "年龄原题")
        self.assertEqual(old_question["libraryVersionNumber"], 1)

        detail = self.owner.get(
            f"/api/library-questions/{library['id']}"
        )
        self.assertEqual(detail.status_code, 200)
        versions = detail.get_json()["data"]["versions"]
        self.assertEqual([item["versionNumber"] for item in versions], [1, 2])
        self.assertEqual(versions[1]["parentVersionId"], versions[0]["id"])

        restored = self.post(
            self.owner,
            f"/api/library-questions/{library['id']}/restore",
            {"versionId": versions[0]["id"]},
        )
        self.assertEqual(restored.status_code, 201)
        restored_question = restored.get_json()["data"]
        self.assertEqual(
            restored_question["currentVersion"]["versionNumber"],
            3,
        )
        self.assertEqual(
            restored_question["currentVersion"]["restoredFromVersionId"],
            versions[0]["id"],
        )
        self.assertEqual(
            restored_question["currentVersion"]["snapshot"]["title"],
            "年龄原题",
        )

        usages = self.owner.get(
            f"/api/library-questions/{library['id']}/usages"
        )
        self.assertEqual(usages.status_code, 200)
        usage_data = usages.get_json()["data"]
        self.assertEqual(usage_data["totalUsages"], 2)
        self.assertEqual(
            {item["surveyId"] for item in usage_data["usages"]},
            {first_survey["id"], second_survey["id"]},
        )

    def test_library_question_cross_survey_statistics(self):
        self.assertEqual(self.register(self.owner, "stats_owner").status_code, 201)
        library = self.create_library_number_question("跨卷年龄")
        first_survey, _ = self.create_survey_with_library_question(
            self.owner,
            "年龄问卷 A",
            library,
            "q_cross00001",
        )
        version_response = self.post(
            self.owner,
            f"/api/library-questions/{library['id']}/versions",
            {
                "snapshot": {
                    **library["currentVersion"]["snapshot"],
                    "title": "跨卷年龄 v2",
                },
                "changeSummary": "调整显示文字",
            },
        )
        self.assertEqual(version_response.status_code, 201)
        library_v2 = version_response.get_json()["data"]
        second_survey, _ = self.create_survey_with_library_question(
            self.owner,
            "年龄问卷 B",
            library_v2,
            "q_cross00002",
        )

        respondent_a = self.app.test_client()
        respondent_b = self.app.test_client()
        self.assertEqual(self.register(respondent_a, "age_user_a").status_code, 201)
        self.assertEqual(self.register(respondent_b, "age_user_b").status_code, 201)
        for client, survey, question_id, value, key in (
            (respondent_a, first_survey, "q_cross00001", 20, "cross-a-0001"),
            (respondent_b, second_survey, "q_cross00002", 30, "cross-b-0001"),
        ):
            submitted = self.post(
                client,
                f"/api/public/surveys/{survey['slug']}/submit",
                {
                    "idempotencyKey": key,
                    "answers": [
                        {"questionId": question_id, "value": value}
                    ],
                },
            )
            self.assertEqual(submitted.status_code, 201, submitted.get_json())

        stats = self.owner.get(
            f"/api/library-questions/{library['id']}/stats"
        )
        self.assertEqual(stats.status_code, 200, stats.get_json())
        data = stats.get_json()["data"]
        self.assertEqual(data["totalSubmissions"], 2)
        self.assertEqual(data["answeredCount"], 2)
        self.assertEqual(data["surveyUsageCount"], 2)
        self.assertEqual(data["versionsIncluded"], [1, 2])
        self.assertEqual(data["numeric"]["average"], 25)
        self.assertEqual(data["numeric"]["values"], [20, 30])

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
