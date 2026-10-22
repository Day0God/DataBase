import unittest

from app.errors import ApiError
from app.validation import (
    evaluate_submission,
    normalize_questions,
    validate_answer,
)


def make_questions():
    return normalize_questions(
        [
            {
                "id": "q_start0001",
                "type": "single",
                "title": "请选择路线",
                "required": True,
                "options": [
                    {"id": "o_route0001", "label": "短路线"},
                    {"id": "o_route0002", "label": "长路线"},
                ],
                "jumps": [
                    {
                        "condition": {"optionId": "o_route0001"},
                        "targetQuestionId": "q_number001",
                    }
                ],
            },
            {
                "id": "q_text00001",
                "type": "text",
                "title": "这段文字应被跳过",
                "required": True,
                "validation": {"minLength": 2, "maxLength": 20},
            },
            {
                "id": "q_number001",
                "type": "number",
                "title": "请输入年龄",
                "required": True,
                "validation": {"min": 0, "max": 120, "integer": True},
                "jumps": [
                    {
                        "condition": {"operator": "gte", "value": 50},
                        "targetQuestionId": "q_finish001",
                    }
                ],
            },
            {
                "id": "q_skip00001",
                "type": "text",
                "title": "高龄路径跳过此题",
                "required": True,
                "validation": {"minLength": 1, "maxLength": 50},
            },
            {
                "id": "q_finish001",
                "type": "text",
                "title": "补充说明",
                "required": False,
                "validation": {"minLength": 0, "maxLength": 100},
            },
        ]
    )


class ValidationTests(unittest.TestCase):
    def test_single_option_jump_skips_questions(self):
        questions = make_questions()
        result = evaluate_submission(
            questions,
            [
                {"questionId": "q_start0001", "value": "o_route0001"},
                {"questionId": "q_number001", "value": 66},
                {"questionId": "q_finish001", "value": "一切正常"},
            ],
        )
        self.assertEqual(
            [answer["questionId"] for answer in result],
            ["q_start0001", "q_number001", "q_finish001"],
        )

    def test_question_skipped_by_jump_does_not_trigger_required_error(self):
        questions = make_questions()
        result = evaluate_submission(
            questions,
            [
                {"questionId": "q_start0001", "value": "o_route0001"},
                {"questionId": "q_number001", "value": 20},
                {"questionId": "q_skip00001", "value": "正常进入"},
            ],
        )
        self.assertEqual(
            [answer["questionId"] for answer in result],
            ["q_start0001", "q_number001", "q_skip00001"],
        )

    def test_missing_reached_required_question_is_rejected(self):
        questions = make_questions()
        with self.assertRaises(ApiError) as context:
            evaluate_submission(
                questions,
                [{"questionId": "q_start0001", "value": "o_route0001"}],
            )
        self.assertEqual(context.exception.code, "VALIDATION_ERROR")

    def test_unvisited_answer_is_rejected(self):
        questions = make_questions()
        with self.assertRaises(ApiError) as context:
            evaluate_submission(
                questions,
                [
                    {"questionId": "q_start0001", "value": "o_route0001"},
                    {"questionId": "q_number001", "value": 60},
                    {"questionId": "q_skip00001", "value": "不应出现"},
                    {"questionId": "q_finish001", "value": ""},
                ],
            )
        self.assertEqual(context.exception.code, "UNEXPECTED_ANSWER")

    def test_number_integer_and_range_validation(self):
        questions = make_questions()
        age = questions[2]
        self.assertFalse(validate_answer(age, 20.5)[0])
        self.assertFalse(validate_answer(age, -1)[0])
        self.assertFalse(validate_answer(age, 121)[0])
        self.assertTrue(validate_answer(age, 20)[0])

    def test_multiple_condition_contains_jump(self):
        questions = normalize_questions(
            [
                {
                    "id": "q_multi0001",
                    "type": "multiple",
                    "title": "选择关注项",
                    "required": True,
                    "options": [
                        {"id": "o_multi0001", "label": "A"},
                        {"id": "o_multi0002", "label": "B"},
                        {"id": "o_multi0003", "label": "C"},
                    ],
                    "validation": {"minSelections": 2, "maxSelections": 3},
                    "jumps": [
                        {
                            "condition": {"optionId": "o_multi0002"},
                            "targetQuestionId": "q_end000001",
                        }
                    ],
                },
                {
                    "id": "q_mid000001",
                    "type": "text",
                    "title": "应跳过",
                    "required": True,
                    "validation": {"minLength": 1, "maxLength": 20},
                },
                {
                    "id": "q_end000001",
                    "type": "text",
                    "title": "终点",
                    "required": False,
                    "validation": {"minLength": 0, "maxLength": 20},
                },
            ]
        )
        result = evaluate_submission(
            questions,
            [{"questionId": "q_multi0001", "value": ["o_multi0001", "o_multi0002"]}],
        )
        self.assertEqual(result[0]["value"], ["o_multi0001", "o_multi0002"])

    def test_backward_jump_is_rejected(self):
        with self.assertRaises(ApiError):
            normalize_questions(
                [
                    {
                        "id": "q_first0001",
                        "type": "single",
                        "title": "第一题",
                        "options": [
                            {"id": "o_first0001", "label": "A"},
                            {"id": "o_first0002", "label": "B"},
                        ],
                        "jumps": [
                            {
                                "condition": {"optionId": "o_first0001"},
                                "targetQuestionId": "q_second001",
                            }
                        ],
                    },
                    {
                        "id": "q_second001",
                        "type": "single",
                        "title": "第二题",
                        "options": [
                            {"id": "o_second001", "label": "A"},
                            {"id": "o_second002", "label": "B"},
                        ],
                        "jumps": [
                            {
                                "condition": {"optionId": "o_second001"},
                                "targetQuestionId": "q_first0001",
                            }
                        ],
                    },
                ]
            )


if __name__ == "__main__":
    unittest.main()
