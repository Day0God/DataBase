import {
  api,
  copyText,
  escapeHtml,
  fromLocalInput,
  randomId,
  setupUserBar,
  statusLabels,
  toLocalInput,
  toast,
  typeLabel,
} from "./api.js";

const surveyId = window.location.pathname.split("/").filter(Boolean).pop();
const loading = document.querySelector("#builderLoading");
const message = document.querySelector("#builderMessage");
const content = document.querySelector("#builderContent");
const questionList = document.querySelector("#questionList");
const questionEmpty = document.querySelector("#questionEmpty");
const builderError = document.querySelector("#builderError");
const publishedNotice = document.querySelector("#publishedNotice");
const titleInput = document.querySelector("#builderTitle");
const descriptionInput = document.querySelector("#builderDescription");
const deadlineInput = document.querySelector("#builderDeadline");
const anonymousInput = document.querySelector("#builderAnonymous");
const multipleInput = document.querySelector("#builderMultiple");
const saveButton = document.querySelector("#saveButton");
const publishButton = document.querySelector("#publishButton");
const closeButton = document.querySelector("#closeButton");
const statsButton = document.querySelector("#statsButton");
const publicLink = document.querySelector("#publicLink");
const copyLinkButton = document.querySelector("#copyLinkButton");
const previewButton = document.querySelector("#previewButton");
const shareHint = document.querySelector("#shareHint");
const shareActions = document.querySelector("#shareActions");
const libraryPicker = document.querySelector("#libraryPicker");
const libraryPickerList = document.querySelector("#libraryPickerList");
const libraryPickerError = document.querySelector("#libraryPickerError");

let state = null;
let busy = false;
let pickerQuestions = [];
let pickerDetail = null;

function showError(value = "") {
  builderError.textContent = value;
  builderError.hidden = !value;
}

function initializeQuestions(data) {
  return data.map((question, index) => ({
    ...question,
    order: index,
    options: question.options || [],
    validation: question.validation || {},
    jumps: question.jumps || [],
  }));
}

function optionRow(option, index, question) {
  return `
    <div class="option-editor ${question.type === "multiple" ? "multi" : ""}">
      <span class="option-bullet">○</span>
      <input value="${escapeHtml(option.label)}" maxlength="200" aria-label="选项 ${index + 1}" data-field="option-label" data-option-index="${index}">
      <button class="icon-button" type="button" data-action="remove-option" data-option-index="${index}" aria-label="删除选项">×</button>
    </div>
  `;
}

function validationControls(question) {
  if (question.type === "multiple") {
    return `
      <div class="subpanel">
        <p class="subpanel-title">选择数量</p>
        <div class="two-columns">
          <label class="field">
            <span class="field-label">最少选择</span>
            <input type="number" min="0" max="${question.options.length}" value="${question.validation.minSelections ?? 0}" data-field="validation-minSelections">
          </label>
          <label class="field">
            <span class="field-label">最多选择</span>
            <input type="number" min="1" max="${question.options.length}" value="${question.validation.maxSelections ?? question.options.length}" data-field="validation-maxSelections">
          </label>
        </div>
      </div>
    `;
  }
  if (question.type === "text") {
    return `
      <div class="subpanel">
        <p class="subpanel-title">文本长度</p>
        <div class="two-columns">
          <label class="field">
            <span class="field-label">最少字符数</span>
            <input type="number" min="0" max="10000" value="${question.validation.minLength ?? 0}" data-field="validation-minLength">
          </label>
          <label class="field">
            <span class="field-label">最多字符数</span>
            <input type="number" min="1" max="10000" value="${question.validation.maxLength ?? 2000}" data-field="validation-maxLength">
          </label>
        </div>
      </div>
    `;
  }
  if (question.type === "number") {
    return `
      <div class="subpanel">
        <p class="subpanel-title">数字限制</p>
        <div class="two-columns">
          <label class="field">
            <span class="field-label">最小值</span>
            <input type="number" step="any" value="${question.validation.min ?? ""}" placeholder="不限" data-field="validation-min">
          </label>
          <label class="field">
            <span class="field-label">最大值</span>
            <input type="number" step="any" value="${question.validation.max ?? ""}" placeholder="不限" data-field="validation-max">
          </label>
        </div>
        <label class="checkbox-row">
          <input type="checkbox" ${question.validation.integer ? "checked" : ""} data-field="validation-integer">
          <span>只允许整数</span>
        </label>
      </div>
    `;
  }
  return "";
}

function conditionSelect(question, jump, jumpIndex) {
  if (question.type === "single" || question.type === "multiple") {
    return `
      <select data-field="jump-condition" data-jump-index="${jumpIndex}" aria-label="跳转条件">
        ${question.options
          .map(
            (option) => `
              <option value="option:${escapeHtml(option.id)}" ${jump.condition.optionId === option.id ? "selected" : ""}>选择「${escapeHtml(option.label)}」</option>
            `,
          )
          .join("")}
      </select>
    `;
  }
  const operatorLabels = {
    eq: "等于",
    neq: "不等于",
    gt: "大于",
    gte: "大于等于",
    lt: "小于",
    lte: "小于等于",
    between: "介于",
  };
  return `
    <select data-field="jump-condition" data-jump-index="${jumpIndex}" aria-label="跳转条件">
      ${Object.entries(operatorLabels)
        .map(
          ([operator, label]) => `
            <option value="operator:${operator}" ${jump.condition.operator === operator ? "selected" : ""}>${label}</option>
          `,
        )
        .join("")}
    </select>
  `;
}

function conditionValue(question, jump, jumpIndex) {
  if (question.type !== "number") return "";
  if (jump.condition.operator === "between") {
    const values = Array.isArray(jump.condition.value)
      ? jump.condition.value
      : [0, 0];
    return `
      <input type="number" step="any" value="${values[0]}" aria-label="区间下限" data-field="jump-between-min" data-jump-index="${jumpIndex}">
      <input type="number" step="any" value="${values[1]}" aria-label="区间上限" data-field="jump-between-max" data-jump-index="${jumpIndex}">
    `;
  }
  return `
    <input type="number" step="any" value="${jump.condition.value ?? 0}" aria-label="比较值" data-field="jump-value" data-jump-index="${jumpIndex}">
  `;
}

function jumpRows(question, questionIndex) {
  const targets = state.questions.slice(questionIndex + 1);
  if (!targets.length) {
    return `
      <div class="subpanel">
        <p class="subpanel-title">条件跳转</p>
        <p class="small muted">这是最后一题，没有可跳转的后续题目。</p>
      </div>
    `;
  }
  return `
    <div class="subpanel">
      <div class="subpanel-title">
        <span>条件跳转</span>
        <button class="button ghost small" type="button" data-action="add-jump">＋ 添加规则</button>
      </div>
      ${question.jumps.length ? "" : '<p class="small muted">未设置跳转时，答完本题进入下一题。</p>'}
      ${question.jumps
        .map((jump, jumpIndex) => {
          const between = question.type === "number" && jump.condition.operator === "between";
          return `
            <div class="jump-row">
              ${conditionSelect(question, jump, jumpIndex)}
              <div class="jump-condition-value">${conditionValue(question, jump, jumpIndex)}</div>
              <span class="jump-arrow">跳到</span>
              <select data-field="jump-target" data-jump-index="${jumpIndex}" aria-label="跳转目标">
                ${targets
                  .map(
                    (target) => `
                      <option value="${escapeHtml(target.id)}" ${jump.targetQuestionId === target.id ? "selected" : ""}>第 ${state.questions.indexOf(target) + 1} 题 · ${escapeHtml((target.title || "未命名题目").slice(0, 20))}</option>
                    `,
                  )
                  .join("")}
              </select>
              <button class="icon-button" type="button" data-action="remove-jump" data-jump-index="${jumpIndex}" aria-label="删除跳转规则">×</button>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function questionEditor(question, index, disabled) {
  const choices = question.type === "single" || question.type === "multiple";
  return `
    <section class="question-editor ${disabled ? "disabled" : ""}" data-qid="${escapeHtml(question.id)}">
      <fieldset class="plain-fieldset" ${disabled ? "disabled" : ""}>
        <div class="question-heading">
          <span class="question-number">${index + 1}</span>
          <div>
            <strong>${typeLabel(question.type)}</strong>
            <div class="small muted">题目 ID：${escapeHtml(question.id)}</div>
            ${
              question.libraryQuestionId
                ? `<span class="source-badge">题库题目 · v${question.libraryVersionNumber}</span>`
                : ""
            }
          </div>
          <div class="inline-actions">
            <button class="icon-button" type="button" data-action="move-up" aria-label="上移" ${index === 0 ? "disabled" : ""}>↑</button>
            <button class="icon-button" type="button" data-action="move-down" aria-label="下移" ${index === state.questions.length - 1 ? "disabled" : ""}>↓</button>
            <button class="icon-button" type="button" data-action="remove-question" aria-label="删除题目">×</button>
          </div>
        </div>
        <div class="question-grid">
          <div class="field">
            <label>题目文本</label>
            <input value="${escapeHtml(question.title)}" maxlength="300" data-field="question-title">
          </div>
          <label class="checkbox-row">
            <input type="checkbox" ${question.required ? "checked" : ""} data-field="question-required">
            <span>必答题</span>
          </label>
          ${
            choices
              ? `
                <div class="subpanel">
                  <div class="subpanel-title">
                    <span>选项</span>
                    <button class="button ghost small" type="button" data-action="add-option">＋ 添加选项</button>
                  </div>
                  <div class="form-stack">
                    ${question.options.map((option, optionIndex) => optionRow(option, optionIndex, question)).join("")}
                  </div>
                </div>
              `
              : ""
          }
          ${validationControls(question)}
          ${choices || question.type === "number" ? jumpRows(question, index) : ""}
        </div>
      </fieldset>
    </section>
  `;
}

function canEditQuestions() {
  return (
    state.survey.status !== "published" &&
    !state.survey.hasResponses
  );
}

function renderQuestions() {
  state.questions.forEach((question, index) => {
    question.order = index;
  });
  const disabled = !canEditQuestions();
  questionList.innerHTML = state.questions
    .map((question, index) => questionEditor(question, index, disabled))
    .join("");
  questionEmpty.hidden = state.questions.length !== 0;
  document.querySelector("#questionToolbar").querySelectorAll("button").forEach((button) => {
    button.disabled = disabled;
  });
}

function renderMeta() {
  const survey = state.survey;
  const status = document.querySelector("#builderStatus");
  document.querySelector("#builderHeading").textContent = survey.title;
  document.querySelector("#builderSubheading").textContent =
    `${state.questions.length} 道题 · 更新于 ${new Date(survey.updatedAt).toLocaleString("zh-CN")}`;
  status.textContent = statusLabels[survey.status];
  status.className = `status-pill ${survey.status}`;
  titleInput.value = survey.title;
  descriptionInput.value = survey.description || "";
  deadlineInput.value = toLocalInput(survey.closesAt);
  anonymousInput.checked = survey.allowAnonymous;
  multipleInput.checked = survey.allowMultipleResponses;
  if (survey.status === "published") {
    publishedNotice.textContent =
      "问卷正在收集回答。请先关闭问卷，再调整题目或跳转规则。";
    publishedNotice.hidden = false;
  } else if (survey.hasResponses) {
    publishedNotice.textContent =
      "问卷已有回答，题目与跳转规则已锁定；仍可返回上面修改说明和设置，然后重新发布。";
    publishedNotice.hidden = false;
  } else {
    publishedNotice.hidden = true;
  }
  publishButton.textContent =
    survey.status === "published"
      ? "重新发布"
      : survey.status === "closed"
        ? "重新开放问卷"
        : "发布问卷";
  closeButton.disabled = survey.status === "closed";
  statsButton.href = `/stats/${survey.id}`;

  const url = `${window.location.origin}${survey.publicPath}`;
  publicLink.textContent =
    survey.status === "published"
      ? url
      : survey.status === "closed"
        ? "重新发布后恢复此链接"
        : "发布后可访问此链接";
  previewButton.href = survey.status === "published" ? survey.publicPath : "#";
  shareHint.textContent =
    survey.status === "published"
      ? "填写者需要登录，再通过此链接进入问卷。"
      : survey.status === "closed"
        ? "问卷当前已关闭，重新发布后原链接恢复可用。"
        : "当前仍是草稿，发布后才会开放填写。";
  shareActions.hidden = survey.status !== "published";
}

function renderAll() {
  renderMeta();
  renderQuestions();
}

function questionByElement(element) {
  const editor = element.closest("[data-qid]");
  if (!editor) return null;
  return state.questions.find((question) => question.id === editor.dataset.qid);
}

function numberOrRaw(value) {
  return value === "" ? "" : Number(value);
}

function updateInput(event) {
  const question = questionByElement(event.target);
  if (!question) return;
  const field = event.target.dataset.field;
  if (!field) return;
  if (field === "question-title") question.title = event.target.value;
  if (field === "option-label") {
    question.options[Number(event.target.dataset.optionIndex)].label = event.target.value;
  }
  if (field === "validation-minSelections") {
    question.validation.minSelections = numberOrRaw(event.target.value);
  }
  if (field === "validation-maxSelections") {
    question.validation.maxSelections = numberOrRaw(event.target.value);
  }
  if (field === "validation-minLength") {
    question.validation.minLength = numberOrRaw(event.target.value);
  }
  if (field === "validation-maxLength") {
    question.validation.maxLength = numberOrRaw(event.target.value);
  }
  if (field === "validation-min") {
    question.validation.min = numberOrRaw(event.target.value);
  }
  if (field === "validation-max") {
    question.validation.max = numberOrRaw(event.target.value);
  }
  if (field === "jump-value") {
    question.jumps[Number(event.target.dataset.jumpIndex)].condition.value =
      Number(event.target.value);
  }
  if (field === "jump-between-min") {
    const condition =
      question.jumps[Number(event.target.dataset.jumpIndex)].condition;
    condition.value[0] = Number(event.target.value);
  }
  if (field === "jump-between-max") {
    const condition =
      question.jumps[Number(event.target.dataset.jumpIndex)].condition;
    condition.value[1] = Number(event.target.value);
  }
}

function updateChange(event) {
  const question = questionByElement(event.target);
  if (!question) return;
  const field = event.target.dataset.field;
  if (field === "question-required") question.required = event.target.checked;
  if (field === "validation-integer") {
    question.validation.integer = event.target.checked;
  }
  if (field === "jump-target") {
    question.jumps[Number(event.target.dataset.jumpIndex)].targetQuestionId =
      event.target.value;
  }
  if (field === "jump-condition") {
    const jump = question.jumps[Number(event.target.dataset.jumpIndex)];
    const [kind, value] = event.target.value.split(":");
    if (kind === "option") {
      jump.condition = {
        optionId: value,
        operator: question.type === "single" ? "option_is" : "contains",
      };
    } else {
      jump.condition = {
        operator: value,
        value: value === "between" ? [0, 0] : 0,
      };
    }
    renderQuestions();
  }
}

function questionDefaults(type) {
  const base = {
    id: randomId("q_"),
    type,
    title: "",
    required: true,
    options: [],
    validation: {},
    jumps: [],
  };
  if (type === "single" || type === "multiple") {
    base.options = [
      { id: randomId("o_"), label: "选项 1" },
      { id: randomId("o_"), label: "选项 2" },
    ];
  }
  if (type === "multiple") {
    base.validation = { minSelections: 0, maxSelections: 2 };
  }
  if (type === "text") {
    base.validation = { minLength: 0, maxLength: 500 };
  }
  if (type === "number") {
    base.validation = { min: null, max: null, integer: false };
  }
  return base;
}

function clickAction(event) {
  const add = event.target.closest("[data-add-type]");
  if (add) {
    state.questions.push(questionDefaults(add.dataset.addType));
    renderQuestions();
    const last = questionList.lastElementChild;
    last?.querySelector('[data-field="question-title"]')?.focus();
    return;
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (!action) return;
  const question = questionByElement(event.target);
  if (!question) return;
  const index = state.questions.indexOf(question);
  if (action === "remove-question") {
    state.questions.splice(index, 1);
    renderQuestions();
  }
  if (action === "move-up" && index > 0) {
    [state.questions[index - 1], state.questions[index]] = [
      state.questions[index],
      state.questions[index - 1],
    ];
    renderQuestions();
  }
  if (action === "move-down" && index < state.questions.length - 1) {
    [state.questions[index + 1], state.questions[index]] = [
      state.questions[index],
      state.questions[index + 1],
    ];
    renderQuestions();
  }
  if (action === "add-option") {
    question.options.push({
      id: randomId("o_"),
      label: `选项 ${question.options.length + 1}`,
    });
    renderQuestions();
  }
  if (action === "remove-option" && question.options.length > 2) {
    question.options.splice(Number(event.target.dataset.optionIndex), 1);
    renderQuestions();
  }
  if (action === "add-jump") {
    const targets = state.questions.slice(index + 1);
    if (!targets.length) return;
    question.jumps.push({
      condition:
        question.type === "number"
          ? { operator: "gte", value: 0 }
          : {
              optionId: question.options[0]?.id,
              operator: question.type === "single" ? "option_is" : "contains",
            },
      targetQuestionId: targets[0].id,
    });
    renderQuestions();
  }
  if (action === "remove-jump") {
    question.jumps.splice(Number(event.target.dataset.jumpIndex), 1);
    renderQuestions();
  }
}

function settingsPayload() {
  return {
    title: titleInput.value,
    description: descriptionInput.value,
    closesAt: fromLocalInput(deadlineInput.value),
    allowAnonymous: anonymousInput.checked,
    allowMultipleResponses: multipleInput.checked,
  };
}

function questionsPayload() {
  return state.questions.map((question, index) => {
    const payload = {
      id: question.id,
      type: question.type,
      title: question.title,
      required: question.required,
      order: index,
      options: question.options,
      validation: question.validation,
      jumps: question.jumps,
    };
    if (question.libraryQuestionId && question.libraryVersionId) {
      payload.libraryQuestionId = question.libraryQuestionId;
      payload.libraryVersionId = question.libraryVersionId;
      payload.libraryVersionNumber = question.libraryVersionNumber;
    }
    return payload;
  });
}

async function saveAll({ quiet = false } = {}) {
  if (busy) return false;
  busy = true;
  showError("");
  saveButton.disabled = true;
  try {
    const survey = await api(`/api/surveys/${surveyId}`, {
      method: "PATCH",
      body: settingsPayload(),
    });
    state.survey = { ...state.survey, ...survey };
    if (canEditQuestions()) {
      state.questions = initializeQuestions(
        await api(`/api/surveys/${surveyId}/questions`, {
          method: "PUT",
          body: { questions: questionsPayload() },
        }),
      );
    }
    renderAll();
    if (!quiet) toast("所有更改已保存");
    return true;
  } catch (error) {
    showError(error.message);
    return false;
  } finally {
    busy = false;
    saveButton.disabled = false;
  }
}

async function publish() {
  const saved = await saveAll({ quiet: true });
  if (!saved) return;
  publishButton.disabled = true;
  try {
    state.survey = await api(`/api/surveys/${surveyId}/publish`, {
      method: "POST",
      body: {},
    });
    renderAll();
    toast("问卷已发布，可以分享填写链接");
  } catch (error) {
    showError(error.message);
  } finally {
    publishButton.disabled = false;
  }
}

async function closeSurvey() {
  if (!window.confirm("关闭后将暂停收集回答，是否继续？")) return;
  closeButton.disabled = true;
  try {
    state.survey = await api(`/api/surveys/${surveyId}/close`, {
      method: "POST",
      body: {},
    });
    renderAll();
    toast("问卷已关闭");
  } catch (error) {
    showError(error.message);
  } finally {
    closeButton.disabled = state.survey.status === "closed";
  }
}

questionList.addEventListener("click", clickAction);
questionList.addEventListener("input", updateInput);
questionList.addEventListener("change", updateChange);
document.querySelector("#questionToolbar").addEventListener("click", clickAction);
saveButton.addEventListener("click", () => saveAll());
publishButton.addEventListener("click", publish);
closeButton.addEventListener("click", closeSurvey);
copyLinkButton.addEventListener("click", () => {
  copyText(`${window.location.origin}${state.survey.publicPath}`);
});

function pickerItem(question) {
  const snapshot = question.currentVersion.snapshot;
  return `
    <button class="library-picker-item" type="button" data-picker-question="${escapeHtml(question.id)}">
      <span>
        <strong>${escapeHtml(snapshot.title)}</strong>
        <small>${typeLabel(snapshot.type)} · ${escapeHtml(question.bankName)} · v${question.currentVersion.versionNumber}</small>
      </span>
      <span>${question.isShared ? `共享自 ${escapeHtml(question.ownerUsername)}` : "我的题目"} →</span>
    </button>
  `;
}

async function openLibraryPicker() {
  libraryPickerError.hidden = true;
  pickerDetail = null;
  libraryPickerList.innerHTML = '<div class="loading">正在读取题库…</div>';
  libraryPicker.hidden = false;
  try {
    pickerQuestions = await api("/api/library-questions?scope=all");
    libraryPickerList.innerHTML = pickerQuestions.length
      ? pickerQuestions.map(pickerItem).join("")
      : '<div class="empty-state"><div><h3>题目库还是空的</h3><p>先到题目库创建或接收共享题目。</p></div></div>';
  } catch (error) {
    libraryPickerList.innerHTML = "";
    libraryPickerError.textContent = error.message;
    libraryPickerError.hidden = false;
  }
}

function closeLibraryPicker() {
  libraryPicker.hidden = true;
  pickerDetail = null;
}

function renderPickerVersions() {
  if (!pickerDetail) return;
  libraryPickerList.innerHTML = `
    <button class="button ghost small" type="button" data-picker-back>← 返回题目列表</button>
    <div class="version-list">
      ${pickerDetail.versions
        .slice()
        .reverse()
        .map(
          (version) => `
            <button class="library-picker-item" type="button" data-picker-version="${escapeHtml(version.id)}">
              <span>
                <strong>v${version.versionNumber} · ${escapeHtml(version.snapshot.title)}</strong>
                <small>${escapeHtml(version.changeSummary || "未填写版本说明")}</small>
              </span>
              <span>${version.versionNumber === pickerDetail.question.currentVersion.versionNumber ? "当前版本" : "使用此版本"} →</span>
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function addLibraryQuestionVersion(version) {
  const libraryQuestion = pickerDetail.question;
  const snapshot = version.snapshot;
  state.questions.push({
    ...snapshot,
    id: randomId("q_"),
    options: snapshot.options.map((option) => ({ ...option })),
    validation: { ...snapshot.validation },
    order: state.questions.length,
    jumps: [],
    libraryQuestionId: libraryQuestion.id,
    libraryVersionId: version.id,
    libraryVersionNumber: version.versionNumber,
  });
  closeLibraryPicker();
  renderQuestions();
  toast(`已加入题库 v${version.versionNumber}，保存问卷后形成独立快照`);
}

document
  .querySelector("#browseLibraryButton")
  .addEventListener("click", openLibraryPicker);
document
  .querySelector("#closeLibraryPicker")
  .addEventListener("click", closeLibraryPicker);
libraryPicker.addEventListener("click", async (event) => {
  if (event.target === libraryPicker) closeLibraryPicker();
  if (event.target.closest("[data-picker-back]")) {
    pickerDetail = null;
    libraryPickerList.innerHTML = pickerQuestions.map(pickerItem).join("");
    return;
  }
  const versionButton = event.target.closest("[data-picker-version]");
  if (versionButton && pickerDetail) {
    const version = pickerDetail.versions.find(
      (item) => item.id === versionButton.dataset.pickerVersion,
    );
    if (version) addLibraryQuestionVersion(version);
    return;
  }
  const item = event.target.closest("[data-picker-question]");
  if (!item) return;
  try {
    libraryPickerList.innerHTML = '<div class="loading">正在读取版本…</div>';
    pickerDetail = await api(
      `/api/library-questions/${item.dataset.pickerQuestion}`,
    );
    renderPickerVersions();
  } catch (error) {
    libraryPickerList.innerHTML = "";
    libraryPickerError.textContent = error.message;
    libraryPickerError.hidden = false;
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !libraryPicker.hidden) {
    closeLibraryPicker();
  }
});

async function initialize() {
  try {
    const me = await api("/api/auth/me");
    setupUserBar(me.user);
    const data = await api(`/api/surveys/${surveyId}`);
    state = {
      survey: data.survey,
      questions: initializeQuestions(data.questions),
    };
    loading.hidden = true;
    content.hidden = false;
    renderAll();
  } catch (error) {
    loading.hidden = true;
    if (error.status === 401) {
      window.location.assign(
        `/login?next=${encodeURIComponent(window.location.pathname)}`,
      );
      return;
    }
    message.hidden = false;
    message.innerHTML = `
      <div>
        <h2>无法打开问卷</h2>
        <p>${escapeHtml(error.message)}</p>
        <a class="button secondary" href="/">返回我的问卷</a>
      </div>
    `;
  }
}

initialize();
