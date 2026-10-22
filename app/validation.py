import math
import secrets
import string
from datetime import datetime, timezone

from .errors import ApiError, ensure

QUESTION_TYPES = {"single", "multiple", "text", "number"}
NUMBER_OPERATORS = {"eq", "neq", "gt", "gte", "lt", "lte", "between"}
ID_PATTERN = r"^[A-Za-z0-9_-]{6,40}$"


def _token(prefix, length=8):
    alphabet = string.ascii_letters + string.digits
    return prefix + "".join(secrets.choice(alphabet) for _ in range(length))


def new_question_id():
    return _token("q_", 9)


def new_option_id():
    return _token("o_", 9)


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _optional_int(value, fallback):
    if value is None or value == "":
        return fallback
    if isinstance(value, bool):
        return math.nan
    try:
        parsed = float(value)
        return int(parsed) if parsed.is_integer() else math.nan
    except (TypeError, ValueError):
        return math.nan


def _optional_number(value, fallback):
    if value is None or value == "":
        return fallback
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ApiError(422, "VALIDATION_ERROR", "截止时间格式无效")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "截止时间格式无效") from exc


def validate_survey_fields(data, partial=False):
    data = data or {}
    result = {}
    if not partial or "title" in data:
        title = _text(data.get("title"))
        ensure(1 <= len(title) <= 120, 422, "VALIDATION_ERROR", "问卷标题应为 1 到 120 个字符")
        result["title"] = title
    if not partial or "description" in data:
        description = data.get("description", "")
        ensure(
            isinstance(description, str) and len(description.strip()) <= 2000,
            422,
            "VALIDATION_ERROR",
            "问卷说明不能超过 2000 个字符",
        )
        result["description"] = description.strip()
    if not partial or "allowAnonymous" in data:
        result["allowAnonymous"] = bool(data.get("allowAnonymous", False))
    if not partial or "allowMultipleResponses" in data:
        result["allowMultipleResponses"] = bool(
            data.get("allowMultipleResponses", False)
        )
    if not partial or "closesAt" in data:
        result["closesAt"] = _parse_date(data.get("closesAt"))
    return result


def _normalize_options(raw_options, question_index):
    ensure(
        isinstance(raw_options, list),
        422,
        "VALIDATION_ERROR",
        f"第 {question_index + 1} 题缺少选项",
    )
    ensure(
        2 <= len(raw_options) <= 50,
        422,
        "VALIDATION_ERROR",
        f"第 {question_index + 1} 题必须有 2 到 50 个选项",
    )
    options = []
    seen = set()
    for option_index, raw_option in enumerate(raw_options):
        raw_option = raw_option if isinstance(raw_option, dict) else {}
        option_id = _text(raw_option.get("id")) or new_option_id()
        label = _text(raw_option.get("label"))
        ensure(
            bool(__import__("re").fullmatch(ID_PATTERN, option_id)),
            422,
            "VALIDATION_ERROR",
            f"第 {question_index + 1} 题的第 {option_index + 1} 个选项 ID 无效",
        )
        ensure(
            option_id not in seen,
            422,
            "VALIDATION_ERROR",
            f"第 {question_index + 1} 题存在重复选项 ID",
        )
        ensure(
            1 <= len(label) <= 200,
            422,
            "VALIDATION_ERROR",
            f"第 {question_index + 1} 题的第 {option_index + 1} 个选项文本应为 1 到 200 字",
        )
        seen.add(option_id)
        options.append({"id": option_id, "label": label})
    return options


def _normalize_question(raw_question, question_index):
    raw_question = raw_question if isinstance(raw_question, dict) else {}
    import re

    question_id = _text(raw_question.get("id")) or new_question_id()
    question_type = _text(raw_question.get("type"))
    title = _text(raw_question.get("title"))
    ensure(
        bool(re.fullmatch(ID_PATTERN, question_id)),
        422,
        "VALIDATION_ERROR",
        f"第 {question_index + 1} 题的题目 ID 无效",
    )
    ensure(
        question_type in QUESTION_TYPES,
        422,
        "VALIDATION_ERROR",
        f"第 {question_index + 1} 题的类型无效",
    )
    ensure(
        1 <= len(title) <= 300,
        422,
        "VALIDATION_ERROR",
        f"第 {question_index + 1} 题的问题文本应为 1 到 300 字",
    )

    question = {
        "id": question_id,
        "type": question_type,
        "title": title,
        "required": bool(raw_question.get("required")),
        "order": question_index,
        "options": [],
        "validation": {},
        "jumps": [],
    }

    if question_type in {"single", "multiple"}:
        question["options"] = _normalize_options(
            raw_question.get("options"),
            question_index,
        )

    validation = raw_question.get("validation") or {}
    if question_type == "multiple":
        min_selections = _optional_int(validation.get("minSelections"), 0)
        max_selections = _optional_int(
            validation.get("maxSelections"),
            len(question["options"]),
        )
        ensure(
            not math.isnan(min_selections)
            and not math.isnan(max_selections)
            and 0 <= min_selections <= max_selections <= len(question["options"])
            and max_selections >= 1,
            422,
            "VALIDATION_ERROR",
            f"第 {question_index + 1} 题的多选数量限制无效",
        )
        question["validation"] = {
            "minSelections": min_selections,
            "maxSelections": max_selections,
        }
    elif question_type == "text":
        min_length = _optional_int(validation.get("minLength"), 0)
        max_length = _optional_int(validation.get("maxLength"), 2000)
        ensure(
            not math.isnan(min_length)
            and not math.isnan(max_length)
            and 0 <= min_length <= max_length <= 10000
            and max_length >= 1,
            422,
            "VALIDATION_ERROR",
            f"第 {question_index + 1} 题的文本长度限制无效",
        )
        question["validation"] = {
            "minLength": min_length,
            "maxLength": max_length,
        }
    elif question_type == "number":
        minimum = _optional_number(validation.get("min"), None)
        maximum = _optional_number(validation.get("max"), None)
        ensure(
            (minimum is None or -1e9 <= minimum <= 1e9)
            and (maximum is None or -1e9 <= maximum <= 1e9)
            and (minimum is None or maximum is None or minimum <= maximum),
            422,
            "VALIDATION_ERROR",
            f"第 {question_index + 1} 题的数字范围无效",
        )
        question["validation"] = {
            "min": minimum,
            "max": maximum,
            "integer": bool(validation.get("integer")),
        }

    raw_jumps = raw_question.get("jumps") or []
    ensure(
        isinstance(raw_jumps, list) and len(raw_jumps) <= 50,
        422,
        "VALIDATION_ERROR",
        f"第 {question_index + 1} 题最多设置 50 条跳转规则",
    )
    for jump_index, raw_jump in enumerate(raw_jumps):
        raw_jump = raw_jump if isinstance(raw_jump, dict) else {}
        target_id = _text(raw_jump.get("targetQuestionId"))
        ensure(
            bool(re.fullmatch(ID_PATTERN, target_id)),
            422,
            "VALIDATION_ERROR",
            f"第 {question_index + 1} 题的第 {jump_index + 1} 条跳转目标无效",
        )
        condition = raw_jump.get("condition") or {}
        if question_type in {"single", "multiple"}:
            option_id = _text(condition.get("optionId"))
            ensure(
                any(option["id"] == option_id for option in question["options"]),
                422,
                "VALIDATION_ERROR",
                f"第 {question_index + 1} 题的第 {jump_index + 1} 条跳转条件选项无效",
            )
            normalized_condition = {
                "optionId": option_id,
                "operator": "option_is"
                if question_type == "single"
                else "contains",
            }
        else:
            ensure(
                question_type == "number",
                422,
                "VALIDATION_ERROR",
                "文本题不能设置条件跳转",
            )
            operator = _text(condition.get("operator"))
            ensure(
                operator in NUMBER_OPERATORS,
                422,
                "VALIDATION_ERROR",
                f"第 {question_index + 1} 题的第 {jump_index + 1} 条数值条件无效",
            )
            value = condition.get("value")
            if operator == "between":
                ensure(
                    isinstance(value, list)
                    and len(value) == 2
                    and _is_number(value[0])
                    and _is_number(value[1])
                    and value[0] <= value[1],
                    422,
                    "VALIDATION_ERROR",
                    f"第 {question_index + 1} 题的第 {jump_index + 1} 条区间条件无效",
                )
            else:
                ensure(
                    _is_number(value),
                    422,
                    "VALIDATION_ERROR",
                    f"第 {question_index + 1} 题的第 {jump_index + 1} 条数值条件无效",
                )
            normalized_condition = {"operator": operator, "value": value}
        question["jumps"].append(
            {
                "condition": normalized_condition,
                "targetQuestionId": target_id,
            }
        )
    return question


def normalize_questions(raw_questions):
    ensure(
        isinstance(raw_questions, list),
        422,
        "VALIDATION_ERROR",
        "questions 必须是数组",
    )
    ensure(
        len(raw_questions) <= 100,
        422,
        "VALIDATION_ERROR",
        "一份问卷最多包含 100 道题",
    )
    questions = [
        _normalize_question(question, index)
        for index, question in enumerate(raw_questions)
    ]
    ids = [question["id"] for question in questions]
    ensure(
        len(ids) == len(set(ids)),
        422,
        "VALIDATION_ERROR",
        "题目 ID 不能重复",
    )
    index_by_id = {question["id"]: index for index, question in enumerate(questions)}
    for question_index, question in enumerate(questions):
        for jump in question["jumps"]:
            target_index = index_by_id.get(jump["targetQuestionId"])
            ensure(
                target_index is not None and target_index > question_index,
                422,
                "VALIDATION_ERROR",
                f"第 {question_index + 1} 题的跳转目标必须是后面的题目",
            )
    return questions


def validate_answer(question, value):
    question_type = question["type"]
    if question_type == "single":
        if not isinstance(value, str) or not any(
            option["id"] == value for option in question["options"]
        ):
            return False, "请选择一个有效选项", None
        return True, "", value

    if question_type == "multiple":
        if (
            not isinstance(value, list)
            or any(not isinstance(item, str) for item in value)
            or len(value) != len(set(value))
            or any(
                not any(option["id"] == item for option in question["options"])
                for item in value
            )
        ):
            return False, "多选答案格式无效", None
        minimum = question["validation"]["minSelections"]
        maximum = question["validation"]["maxSelections"]
        if len(value) < minimum:
            return False, f"至少选择 {minimum} 项", None
        if len(value) > maximum:
            return False, f"最多选择 {maximum} 项", None
        return True, "", value

    if question_type == "text":
        if not isinstance(value, str):
            return False, "请输入文本内容", None
        normalized = value.strip()
        minimum = question["validation"]["minLength"]
        maximum = question["validation"]["maxLength"]
        if len(normalized) < minimum:
            return False, f"至少输入 {minimum} 个字符", None
        if len(normalized) > maximum:
            return False, f"最多输入 {maximum} 个字符", None
        return True, "", normalized

    if question_type == "number":
        if isinstance(value, bool) or value is None or value == "":
            return False, "请输入有效数字", None
        try:
            normalized = float(value)
        except (TypeError, ValueError):
            return False, "请输入有效数字", None
        if not math.isfinite(normalized):
            return False, "请输入有效数字", None
        if question["validation"]["integer"] and not normalized.is_integer():
            return False, "请输入整数", None
        minimum = question["validation"]["min"]
        maximum = question["validation"]["max"]
        if minimum is not None and normalized < minimum:
            return False, f"数值不能小于 {minimum}", None
        if maximum is not None and normalized > maximum:
            return False, f"数值不能大于 {maximum}", None
        if normalized.is_integer():
            normalized = int(normalized)
        return True, "", normalized

    return False, "未知题型", None


def jump_matches(condition, answer):
    operator = condition["operator"]
    if operator == "option_is":
        return answer == condition["optionId"]
    if operator == "contains":
        return isinstance(answer, list) and condition["optionId"] in answer

    value = float(answer)
    expected = condition["value"]
    if operator == "eq":
        return value == expected
    if operator == "neq":
        return value != expected
    if operator == "gt":
        return value > expected
    if operator == "gte":
        return value >= expected
    if operator == "lt":
        return value < expected
    if operator == "lte":
        return value <= expected
    if operator == "between":
        return expected[0] <= value <= expected[1]
    return False


def _is_empty(value):
    return value is None or value == "" or (isinstance(value, list) and not value)


def evaluate_submission(questions, raw_answers):
    ensure(
        isinstance(raw_answers, list),
        422,
        "VALIDATION_ERROR",
        "answers 必须是数组",
    )
    answer_map = {}
    for answer in raw_answers:
        answer = answer if isinstance(answer, dict) else {}
        question_id = _text(answer.get("questionId"))
        ensure(
            question_id and question_id not in answer_map,
            422,
            "VALIDATION_ERROR",
            "答案中存在无效或重复的题目 ID",
        )
        answer_map[question_id] = answer.get("value")

    index_by_id = {
        question["id"]: index for index, question in enumerate(questions)
    }
    visited = set()
    result = []
    current_index = 0

    while current_index < len(questions):
        question = questions[current_index]
        if question["id"] in answer_map:
            visited.add(question["id"])
        value = answer_map.get(question["id"])
        if _is_empty(value):
            if question["required"]:
                raise ApiError(
                    422,
                    "VALIDATION_ERROR",
                    f'第 {current_index + 1} 题“{question["title"]}”为必答题',
                    {"questionId": question["id"]},
                )
            current_index += 1
            continue

        valid, message, normalized = validate_answer(question, value)
        if not valid:
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                f"第 {current_index + 1} 题：{message}",
                {"questionId": question["id"]},
            )
        result.append({"questionId": question["id"], "value": normalized})

        matched_jump = next(
            (
                jump
                for jump in question["jumps"]
                if jump_matches(jump["condition"], normalized)
            ),
            None,
        )
        if not matched_jump:
            current_index += 1
            continue
        target_index = index_by_id.get(matched_jump["targetQuestionId"])
        if target_index is None or target_index <= current_index:
            raise ApiError(
                500,
                "INVALID_JUMP_CONFIGURATION",
                "问卷跳转配置无效，请联系问卷创建者",
            )
        current_index = target_index

    for question_id in answer_map:
        if question_id not in visited:
            raise ApiError(
                422,
                "UNEXPECTED_ANSWER",
                "提交内容包含未到达题目的答案，请刷新页面后重试",
                {"questionId": question_id},
            )
    return result
