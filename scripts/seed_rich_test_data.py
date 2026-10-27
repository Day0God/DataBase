"""Create a reproducible rich survey and question-library test dataset."""

import sys
from pathlib import Path

from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app


MONGODB_URI = "mongodb://127.0.0.1:27018"
DATABASE_NAME = "dm_rich_visual_20261027"
PASSWORD = "RichTest123"

QUESTIONS = [
    {
        "id": "q_rich_role01",
        "type": "single",
        "title": "你目前的主要身份是？",
        "required": True,
        "options": [
            {"id": "o_rich_stu01", "label": "学生"},
            {"id": "o_rich_tea01", "label": "教师"},
            {"id": "o_rich_eng01", "label": "工程师"},
            {"id": "o_rich_res01", "label": "研究人员"},
        ],
        "jumps": [
            {
                "condition": {"optionId": "o_rich_stu01"},
                "targetQuestionId": "q_rich_hours",
            }
        ],
    },
    {
        "id": "q_rich_skill",
        "type": "multiple",
        "title": "你最关注哪些能力？",
        "required": True,
        "options": [
            {"id": "o_rich_code1", "label": "数据分析"},
            {"id": "o_rich_comm1", "label": "沟通表达"},
            {"id": "o_rich_team1", "label": "团队协作"},
            {"id": "o_rich_lead1", "label": "项目管理"},
        ],
        "validation": {"minSelections": 1, "maxSelections": 3},
        "jumps": [],
    },
    {
        "id": "q_rich_hours",
        "type": "number",
        "title": "你每周投入多少小时？",
        "required": True,
        "validation": {"min": 0, "max": 60, "integer": True},
        "jumps": [
            {
                "condition": {"operator": "gte", "value": 20},
                "targetQuestionId": "q_rich_dimension",
            }
        ],
    },
    {
        "id": "q_rich_course",
        "type": "text",
        "title": "你正在学习或教授哪门课程？",
        "required": True,
        "validation": {"minLength": 2, "maxLength": 80},
        "jumps": [],
    },
    {
        "id": "q_rich_dimension",
        "type": "multiple",
        "title": "请选择你重视的体验维度（1-2 项）",
        "required": True,
        "options": [
            {"id": "o_rich_con1", "label": "内容质量"},
            {"id": "o_rich_pra1", "label": "实践收获"},
            {"id": "o_rich_int1", "label": "互动体验"},
            {"id": "o_rich_car1", "label": "职业帮助"},
        ],
        "validation": {"minSelections": 1, "maxSelections": 2},
        "jumps": [],
    },
    {
        "id": "q_rich_score",
        "type": "number",
        "title": "请给整体体验评分（1-5 分）",
        "required": True,
        "validation": {"min": 1, "max": 5, "integer": True},
        "jumps": [
            {
                "condition": {"operator": "lte", "value": 2},
                "targetQuestionId": "q_rich_improve",
            }
        ],
    },
    {
        "id": "q_rich_best",
        "type": "text",
        "title": "最满意的地方是什么？",
        "required": True,
        "validation": {"minLength": 3, "maxLength": 200},
        "jumps": [],
    },
    {
        "id": "q_rich_improve",
        "type": "text",
        "title": "最需要改进的地方是什么？",
        "required": True,
        "validation": {"minLength": 5, "maxLength": 500},
        "jumps": [],
    },
]


def assert_response(response, status, label):
    if response.status_code != status:
        raise RuntimeError(
            f"{label}: expected {status}, got {response.status_code}: "
            f"{response.get_data(as_text=True)}"
        )
    return response.get_json().get("data") if response.is_json else None


def register(client, username):
    return assert_response(
        client.post(
            "/api/auth/register",
            json={"username": username, "password": PASSWORD},
        ),
        201,
        f"register {username}",
    )["user"]


def create_library_question(client, bank_id, question):
    return assert_response(
        client.post(
            "/api/library-questions",
            json={
                "bankId": bank_id,
                "question": question,
                "changeSummary": "综合统计测试",
            },
        ),
        201,
        f"create library question {question['title']}",
    )


def create_survey(client, title, questions):
    survey = assert_response(
        client.post(
            "/api/surveys",
            json={
                "title": title,
                "description": "用于验证复杂路径、题库版本和统计口径",
                "allowAnonymous": False,
                "allowMultipleResponses": True,
            },
        ),
        201,
        f"create survey {title}",
    )
    assert_response(
        client.put(
            f"/api/surveys/{survey['id']}/questions",
            json={"questions": questions},
        ),
        200,
        f"save questions {title}",
    )
    assert_response(
        client.post(f"/api/surveys/{survey['id']}/publish", json={}),
        200,
        f"publish survey {title}",
    )
    return survey


def submit(client, survey, answers, key):
    return assert_response(
        client.post(
            f"/api/public/surveys/{survey['slug']}/submit",
            json={"idempotencyKey": key, "answers": answers},
        ),
        201,
        f"submit {survey['title']}",
    )


def print_survey_stats(client, survey, question_count):
    data = assert_response(
        client.get(f"/api/surveys/{survey['id']}/stats"),
        200,
        f"stats {survey['title']}",
    )
    by_id = {item["id"]: item for item in data["questions"]}
    print(f"\nSURVEY={survey['title']} ID={survey['id']} SLUG={survey['slug']}")
    print(f"SUBMISSIONS={data['totalSubmissions']} QUESTIONS={question_count}")
    print(f"ROLE_COUNTS={[item['count'] for item in by_id['q_rich_role01']['options']]}")
    print(f"SKILL_ANSWERED={by_id['q_rich_skill']['answeredCount']}")
    print(f"COURSE_ANSWERED={by_id['q_rich_course']['answeredCount']}")
    print(f"HOURS={by_id['q_rich_hours']['numeric']}")
    print(f"DIMENSION_COUNTS={[item['count'] for item in by_id['q_rich_dimension']['options']]}")
    print(f"SCORE={by_id['q_rich_score']['numeric']}")
    print(f"BEST_ANSWERED={by_id['q_rich_best']['answeredCount']}")
    print(f"IMPROVE_ANSWERED={by_id['q_rich_improve']['answeredCount']}")


def main():
    mongo_client = MongoClient(MONGODB_URI, tz_aware=True)
    mongo_client.drop_database(DATABASE_NAME)
    database = mongo_client[DATABASE_NAME]
    app = create_app(database)
    app.config.update(TESTING=True)

    owner = app.test_client()
    teacher = app.test_client()
    student_a = app.test_client()
    engineer = app.test_client()
    partner = app.test_client()

    register(owner, "rich_owner")
    register(teacher, "rich_teacher")
    register(student_a, "rich_student")
    register(engineer, "rich_engineer")
    partner_user = register(partner, "rich_partner")

    bank = assert_response(
        owner.post(
            "/api/question-banks",
            json={
                "name": "综合测评题库",
                "description": "复杂测试使用的可复用题目",
            },
        ),
        201,
        "create bank",
    )
    library_questions = {}
    for source in QUESTIONS:
        library_questions[source["id"]] = create_library_question(
            owner,
            bank["id"],
            source,
        )

    hours_v1 = library_questions["q_rich_hours"]
    hours_v2 = assert_response(
        owner.post(
            f"/api/library-questions/{hours_v1['id']}/versions",
            json={
                "baseVersionId": hours_v1["currentVersion"]["id"],
                "snapshot": {
                    **hours_v1["currentVersion"]["snapshot"],
                    "title": "你每周投入多少小时？（扩展版）",
                    "validation": {"min": 0, "max": 80, "integer": True},
                },
                "changeSummary": "提高上限到 80 小时",
            },
        ),
        201,
        "create hours v2",
    )
    hours_v3 = assert_response(
        owner.post(
            f"/api/library-questions/{hours_v1['id']}/restore",
            json={"versionId": hours_v1["currentVersion"]["id"]},
        ),
        201,
        "restore hours v1",
    )
    assert_response(
        owner.post(
            f"/api/library-questions/{hours_v1['id']}/share",
            json={"username": "rich_partner"},
        ),
        200,
        "share hours question",
    )

    base_questions = [{**question, "order": index} for index, question in enumerate(QUESTIONS)]
    base_questions[2].update(
        {
            "libraryQuestionId": hours_v1["id"],
            "libraryVersionId": hours_v1["currentVersion"]["id"],
            "libraryVersionNumber": 1,
        }
    )
    comprehensive = create_survey(
        owner,
        "综合能力与体验调查（复杂版）",
        base_questions,
    )

    tracking_question = {
        **hours_v2["currentVersion"]["snapshot"],
        "id": "q_rich_hours_v2",
        "order": 0,
        "jumps": [],
        "libraryQuestionId": hours_v1["id"],
        "libraryVersionId": hours_v2["currentVersion"]["id"],
        "libraryVersionNumber": 2,
    }
    tracking = create_survey(
        owner,
        "每周投入跟踪",
        [tracking_question],
    )

    shared_question_doc = {
        **hours_v3["currentVersion"]["snapshot"],
        "id": "q_rich_hours_v3",
        "order": 0,
        "jumps": [],
        "libraryQuestionId": hours_v1["id"],
        "libraryVersionId": hours_v3["currentVersion"]["id"],
        "libraryVersionNumber": 3,
    }
    partner_survey = create_survey(
        partner,
        "共享题目协作调查",
        [shared_question_doc],
    )

    complex_answers = [
        (
            student_a,
            [
                {"questionId": "q_rich_role01", "value": "o_rich_stu01"},
                {"questionId": "q_rich_hours", "value": 25},
                {"questionId": "q_rich_dimension", "value": ["o_rich_con1", "o_rich_pra1"]},
                {"questionId": "q_rich_score", "value": 2},
                {"questionId": "q_rich_improve", "value": "希望增加更多实践案例"},
            ],
            "rich-student-0001",
        ),
        (
            teacher,
            [
                {"questionId": "q_rich_role01", "value": "o_rich_stu01"},
                {"questionId": "q_rich_hours", "value": 8},
                {"questionId": "q_rich_course", "value": "数据库系统"},
                {"questionId": "q_rich_dimension", "value": ["o_rich_con1"]},
                {"questionId": "q_rich_score", "value": 5},
                {"questionId": "q_rich_best", "value": "结构清晰"},
                {"questionId": "q_rich_improve", "value": "希望增加更多案例"},
            ],
            "rich-teacher-0001",
        ),
        (
            engineer,
            [
                {"questionId": "q_rich_role01", "value": "o_rich_eng01"},
                {"questionId": "q_rich_skill", "value": ["o_rich_code1", "o_rich_lead1"]},
                {"questionId": "q_rich_hours", "value": 40},
                {"questionId": "q_rich_dimension", "value": ["o_rich_pra1", "o_rich_int1"]},
                {"questionId": "q_rich_score", "value": 4},
                {"questionId": "q_rich_best", "value": "题目贴近实际工作"},
                {"questionId": "q_rich_improve", "value": "希望增加统计导出"},
            ],
            "rich-engineer-0001",
        ),
    ]
    for client, answers, key in complex_answers:
        submit(client, comprehensive, answers, key)

    # Add one more non-student path with a low score.
    non_student_low = app.test_client()
    register(non_student_low, "rich_researcher")
    submit(
        non_student_low,
        comprehensive,
        [
            {"questionId": "q_rich_role01", "value": "o_rich_tea01"},
            {"questionId": "q_rich_skill", "value": ["o_rich_comm1", "o_rich_team1"]},
            {"questionId": "q_rich_hours", "value": 10},
            {"questionId": "q_rich_course", "value": "教育研究方法"},
            {"questionId": "q_rich_dimension", "value": ["o_rich_car1"]},
            {"questionId": "q_rich_score", "value": 2},
            {"questionId": "q_rich_improve", "value": "流程仍然偏长"},
        ],
        "rich-researcher-0001",
    )
    submit(
        student_a,
        comprehensive,
        [
            {"questionId": "q_rich_role01", "value": "o_rich_stu01"},
            {"questionId": "q_rich_hours", "value": 12},
            {"questionId": "q_rich_course", "value": "数据结构"},
            {"questionId": "q_rich_dimension", "value": ["o_rich_con1"]},
            {"questionId": "q_rich_score", "value": 1},
            {"questionId": "q_rich_improve", "value": "希望增加练习反馈"},
        ],
        "rich-student-repeat-0002",
    )
    submit(
        teacher,
        comprehensive,
        [
            {"questionId": "q_rich_role01", "value": "o_rich_tea01"},
            {"questionId": "q_rich_skill", "value": ["o_rich_comm1"]},
            {"questionId": "q_rich_hours", "value": 32},
            {"questionId": "q_rich_dimension", "value": ["o_rich_int1", "o_rich_car1"]},
            {"questionId": "q_rich_score", "value": 4},
            {"questionId": "q_rich_best", "value": "统计分析清晰"},
            {"questionId": "q_rich_improve", "value": "希望支持分组对比"},
        ],
        "rich-teacher-repeat-0002",
    )

    submit(
        student_a,
        tracking,
        [{"questionId": "q_rich_hours_v2", "value": 5}],
        "tracking-student-0001",
    )
    submit(
        teacher,
        tracking,
        [{"questionId": "q_rich_hours_v2", "value": 15}],
        "tracking-teacher-0001",
    )
    submit(
        student_a,
        tracking,
        [{"questionId": "q_rich_hours_v2", "value": 7}],
        "tracking-student-0002",
    )
    submit(
        teacher,
        tracking,
        [{"questionId": "q_rich_hours_v2", "value": 18}],
        "tracking-teacher-0002",
    )
    submit(
        partner,
        partner_survey,
        [{"questionId": "q_rich_hours_v3", "value": 30}],
        "partner-hours-0001",
    )

    print_survey_stats(owner, comprehensive, 8)
    cross_stats = assert_response(
        owner.get(f"/api/library-questions/{hours_v1['id']}/stats"),
        200,
        "cross-survey stats",
    )
    usages = assert_response(
        owner.get(f"/api/library-questions/{hours_v1['id']}/usages"),
        200,
        "library usages",
    )
    print("\nLIBRARY_CROSS_STATS")
    print(f"QUESTION_ID={hours_v1['id']}")
    print(f"USAGES={usages['totalUsages']}")
    print(f"SURVEY_COUNT={cross_stats['surveyUsageCount']}")
    print(f"SUBMISSIONS={cross_stats['totalSubmissions']}")
    print(f"VERSIONS={cross_stats['versionsIncluded']}")
    print(f"NUMERIC={cross_stats['numeric']}")
    print("\nUSERS=rich_owner rich_teacher rich_student rich_engineer rich_researcher rich_partner")
    print(f"PASSWORD={PASSWORD}")
    print(f"DATABASE={DATABASE_NAME}")
    print(f"COMPLEX_SURVEY=\"/survey/{comprehensive['slug']}\"")
    print(f"TRACKING_SURVEY=\"/survey/{tracking['slug']}\"")
    print(f"PARTNER_SURVEY=\"/survey/{partner_survey['slug']}\"")
    mongo_client.close()


if __name__ == "__main__":
    main()
