import {
  api,
  escapeHtml,
  formatDate,
  setupUserBar,
  typeLabel,
} from "./api.js";

const loading = document.querySelector("#surveyLoading");
const content = document.querySelector("#surveyContent");
const message = document.querySelector("#surveyMessage");
const wizard = document.querySelector("#wizard");
const completion = document.querySelector("#completion");
const questionCard = document.querySelector("#questionCard");
const answerError = document.querySelector("#answerError");
const progress = document.querySelector("#wizardProgress");
const progressText = document.querySelector("#wizardProgressText");
const backButton = document.querySelector("#backButton");
const nextButton = document.querySelector("#nextButton");

const slug = decodeURIComponent(window.location.pathname.split("/").filter(Boolean).pop());
let survey = null;
let current = null;
let history = [];
let answers = {};
let submitting = false;
let idempotencyKey = crypto.randomUUID();

function showMessage(title, body, action = "") {
  loading.hidden = true;
  content.hidden = true;
  message.hidden = false;
  message.innerHTML = `
    <div>
      <h2>${escapeHtml(title)}</h2>
      <p>${escapeHtml(body)}</p>
      ${action}
    </div>
  `;
}

function showError(messageValue) {
  answerError.textContent = messageValue;
  answerError.hidden = !messageValue;
}

function questionIndex(questionId) {
  return survey.questions.findIndex((question) => question.id === questionId);
}

function clearDownstreamAnswers(question) {
  const order = question.order;
  for (const item of survey.questions) {
    if (item.order > order) delete answers[item.id];
  }
}

function isEmpty(value) {
  return (
    value === undefined ||
    value === null ||
    value === "" ||
    (Array.isArray(value) && value.length === 0)
  );
}

function validateCurrent() {
  const value = answers[current.id];
  if (isEmpty(value)) {
    if (current.required) return `第 ${current.order + 1} 题是必答题，请回答后再继续。`;
    return "";
  }
  if (current.type === "multiple") {
    const minimum = current.validation.minSelections;
    const maximum = current.validation.maxSelections;
    if (value.length < minimum) return `至少选择 ${minimum} 项。`;
    if (value.length > maximum) return `最多选择 ${maximum} 项。`;
  }
  if (current.type === "text") {
    const normalized = value.trim();
    if (normalized.length < current.validation.minLength) {
      return `至少输入 ${current.validation.minLength} 个字符。`;
    }
    if (normalized.length > current.validation.maxLength) {
      return `最多输入 ${current.validation.maxLength} 个字符。`;
    }
  }
  if (current.type === "number") {
    const number = Number(value);
    if (!Number.isFinite(number)) return "请输入有效数字。";
    if (current.validation.integer && !Number.isInteger(number)) return "请输入整数。";
    if (current.validation.min !== null && number < current.validation.min) {
      return `数值不能小于 ${current.validation.min}。`;
    }
    if (current.validation.max !== null && number > current.validation.max) {
      return `数值不能大于 ${current.validation.max}。`;
    }
  }
  return "";
}

function jumpMatches(condition, value) {
  if (condition.operator === "option_is") return value === condition.optionId;
  if (condition.operator === "contains") {
    return Array.isArray(value) && value.includes(condition.optionId);
  }
  const number = Number(value);
  const expected = condition.value;
  return {
    eq: number === expected,
    neq: number !== expected,
    gt: number > expected,
    gte: number >= expected,
    lt: number < expected,
    lte: number <= expected,
    between: number >= expected[0] && number <= expected[1],
  }[condition.operator] || false;
}

function nextId() {
  const value = answers[current.id];
  if (!isEmpty(value)) {
    const jump = current.jumps.find((item) =>
      jumpMatches(item.condition, value),
    );
    if (jump) return jump.targetQuestionId;
  }
  const index = questionIndex(current.id);
  return survey.questions[index + 1]?.id || null;
}

function renderControls() {
  if (current.type === "single") {
    return `
      <div class="choice-list">
        ${current.options
          .map(
            (option) => `
              <label class="choice">
                <input type="radio" name="answer" value="${escapeHtml(option.id)}" ${answers[current.id] === option.id ? "checked" : ""}>
                <span>${escapeHtml(option.label)}</span>
              </label>
            `,
          )
          .join("")}
      </div>
    `;
  }
  if (current.type === "multiple") {
    const selected = Array.isArray(answers[current.id]) ? answers[current.id] : [];
    const minimum = current.validation.minSelections;
    const maximum = current.validation.maxSelections;
    return `
      <p class="field-hint">请选择 ${minimum} 至 ${maximum} 项</p>
      <div class="choice-list">
        ${current.options
          .map(
            (option) => `
              <label class="choice">
                <input type="checkbox" name="answer" value="${escapeHtml(option.id)}" ${selected.includes(option.id) ? "checked" : ""}>
                <span>${escapeHtml(option.label)}</span>
              </label>
            `,
          )
          .join("")}
      </div>
    `;
  }
  if (current.type === "number") {
    const constraints = [];
    if (current.validation.min !== null) constraints.push(`最小值 ${current.validation.min}`);
    if (current.validation.max !== null) constraints.push(`最大值 ${current.validation.max}`);
    if (current.validation.integer) constraints.push("必须为整数");
    return `
      <div class="field">
        <label for="textAnswer">你的回答</label>
        <input id="textAnswer" name="answer" type="number" inputmode="decimal" value="${escapeHtml(answers[current.id] ?? "")}" ${current.validation.integer ? 'step="1"' : 'step="any"'} ${current.validation.min !== null ? `min="${current.validation.min}"` : ""} ${current.validation.max !== null ? `max="${current.validation.max}"` : ""}>
        <span class="field-hint">${escapeHtml(constraints.join(" · ") || "请输入一个数字")}</span>
      </div>
    `;
  }
  return `
    <div class="field">
      <label for="textAnswer">你的回答</label>
      <textarea id="textAnswer" name="answer" maxlength="${current.validation.maxLength}" placeholder="请输入内容">${escapeHtml(answers[current.id] ?? "")}</textarea>
      <span class="field-hint">${current.validation.minLength}–${current.validation.maxLength} 个字符</span>
    </div>
  `;
}

function renderCurrent() {
  showError("");
  const answeredCount = survey.questions.filter(
    (question) => !isEmpty(answers[question.id]),
  ).length;
  progress.max = Math.max(survey.questions.length, 1);
  progress.value = answeredCount;
  progressText.textContent = `已完成 ${answeredCount} 道 · 第 ${current.order + 1} 题`;
  backButton.hidden = history.length === 0;
  nextButton.textContent = nextId() === null ? "提交问卷" : "下一题 →";
  questionCard.innerHTML = `
    <p class="question-kicker">${typeLabel(current.type)} · ${current.order + 1}</p>
    <h2>${escapeHtml(current.title)}${current.required ? '<span class="required-mark" title="必答">*</span>' : ""}</h2>
    ${renderControls()}
  `;
  const input = questionCard.querySelector("input, textarea");
  if (input) setTimeout(() => input.focus(), 20);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateAnswerFromControl(event) {
  clearDownstreamAnswers(current);
  if (current.type === "single") {
    if (event.target.matches('input[name="answer"]')) {
      answers[current.id] = event.target.value;
    }
  } else if (current.type === "multiple") {
    answers[current.id] = Array.from(
      questionCard.querySelectorAll('input[name="answer"]:checked'),
      (input) => input.value,
    );
    nextButton.textContent = nextId() === null ? "提交问卷" : "下一题 →";
  } else {
    answers[current.id] = event.target.value;
  }
  showError("");
}

function answerPayload() {
  return survey.questions
    .filter((question) => !isEmpty(answers[question.id]))
    .map((question) => ({
      questionId: question.id,
      value:
        question.type === "number"
          ? Number(answers[question.id])
          : answers[question.id],
    }));
}

async function submit() {
  if (submitting) return;
  submitting = true;
  nextButton.disabled = true;
  nextButton.textContent = "正在提交…";
  try {
    await api(`/api/public/surveys/${encodeURIComponent(slug)}/submit`, {
      method: "POST",
      body: {
        answers: answerPayload(),
        idempotencyKey,
      },
    });
    wizard.hidden = true;
    completion.hidden = false;
    document.querySelector("#completionMessage").textContent = survey.allowAnonymous
      ? "感谢你的回答。本问卷匿名收集，统计中不会显示你的账号身份。"
      : "感谢你的回答，你的提交已经安全保存。";
    completion.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (error.code === "ALREADY_SUBMITTED") {
      showMessage("已经填写过", "这份问卷不允许同一账号重复填写。");
      return;
    }
    if (error.details?.questionId) {
      const target = survey.questions.find(
        (question) => question.id === error.details.questionId,
      );
      if (target) {
        history = [];
        current = target;
      }
    }
    showError(error.message);
    if (current) renderCurrent();
    showError(error.message);
  } finally {
    submitting = false;
    nextButton.disabled = false;
    if (current) nextButton.textContent = nextId() === null ? "提交问卷" : "下一题 →";
  }
}

function advance() {
  const error = validateCurrent();
  if (error) {
    showError(error);
    return;
  }
  const targetId = nextId();
  if (targetId === null) {
    submit();
    return;
  }
  history.push(current.id);
  current = survey.questions.find((question) => question.id === targetId);
  renderCurrent();
}

backButton.addEventListener("click", () => {
  const previousId = history.pop();
  if (!previousId) return;
  current = survey.questions.find((question) => question.id === previousId);
  renderCurrent();
});

nextButton.addEventListener("click", advance);
questionCard.addEventListener("change", updateAnswerFromControl);
questionCard.addEventListener("input", (event) => {
  if (event.target.matches("textarea, input[type=number]")) {
    updateAnswerFromControl(event);
  }
});

async function initialize() {
  try {
    const me = await api("/api/auth/me");
    setupUserBar(me.user);
  } catch (error) {
    if (error.status === 401) {
      const next = `${window.location.pathname}${window.location.search}`;
      window.location.assign(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    showMessage("无法打开问卷", error.message, '<a class="button secondary" href="/">返回首页</a>');
    return;
  }

  try {
    survey = await api(`/api/public/surveys/${encodeURIComponent(slug)}`);
    loading.hidden = true;
    content.hidden = false;
    document.title = `${survey.title} · MongoForm`;
    document.querySelector("#surveyTitle").textContent = survey.title;
    document.querySelector("#surveyDescription").textContent =
      survey.description || "感谢你抽出时间完成这份问卷。";
    document.querySelector("#surveyKicker").textContent = survey.allowAnonymous
      ? "Anonymous response"
      : "Signed-in response";
    document.querySelector("#surveyMeta").innerHTML = `
      <span>${survey.questions.length} 道题</span>
      <span>${survey.allowAnonymous ? "匿名统计" : "实名统计"}</span>
      <span>${survey.allowMultipleResponses ? "可多次填写" : "每人一次"}</span>
    `;
    document.querySelector("#wizardDeadline").textContent = survey.closesAt
      ? `截止 ${formatDate(survey.closesAt)}`
      : "不限截止时间";

    if (!survey.canRespond) {
      showMessage(
        "这份问卷你已经填写过了",
        "问卷创建者设置了每个账号只能提交一次。",
        '<a class="button secondary" href="/">返回首页</a>',
      );
      return;
    }
    if (!survey.questions.length) {
      showMessage("问卷暂无题目", "请联系问卷创建者检查发布状态。");
      return;
    }
    wizard.hidden = false;
    current = survey.questions[0];
    renderCurrent();
  } catch (error) {
    const action =
      error.code === "AUTH_REQUIRED"
        ? `<a class="button" href="/login?next=${encodeURIComponent(window.location.pathname)}">登录后填写</a>`
        : '<a class="button secondary" href="/">返回首页</a>';
    showMessage(
      error.code === "SURVEY_NOT_ACTIVE" ? "问卷已停止收集" : "无法打开问卷",
      error.message,
      action,
    );
  }
}

initialize();
