import {
  api,
  escapeHtml,
  formatDate,
  randomId,
  setupUserBar,
  toast,
  typeLabel,
} from "./api.js";

const loading = document.querySelector("#libraryLoading");
const message = document.querySelector("#libraryMessage");
const content = document.querySelector("#libraryContent");
const bankList = document.querySelector("#bankList");
const bankFilter = document.querySelector("#libraryBankFilter");
const scopeFilter = document.querySelector("#libraryScopeFilter");
const searchInput = document.querySelector("#librarySearch");
const questionList = document.querySelector("#libraryQuestionList");
const questionEmpty = document.querySelector("#libraryQuestionEmpty");
const detailDialog = document.querySelector("#libraryQuestionDialog");
const detailBody = document.querySelector("#libraryQuestionDetail");
const detailError = document.querySelector("#libraryQuestionError");
const createDialog = document.querySelector("#libraryCreateDialog");
const createForm = document.querySelector("#libraryQuestionForm");
const createError = document.querySelector("#libraryCreateError");

let banks = [];
let questions = [];
let selectedDetail = null;

function setError(element, value = "") {
  element.textContent = value;
  element.hidden = !value;
}

function bankById(bankId) {
  return banks.find((bank) => bank.id === bankId);
}

function renderBanks() {
  const selectedBank = bankFilter.value;
  bankList.innerHTML = banks
    .map(
      (bank) => `
        <button class="bank-item ${bankFilter.value === bank.id ? "active" : ""}" type="button" data-bank-id="${escapeHtml(bank.id)}">
          <span>
            <strong>${escapeHtml(bank.name)}</strong>
            <small>${bank.questionCount} 道题</small>
          </span>
          <span aria-hidden="true">→</span>
        </button>
      `,
    )
    .join("");
  document.querySelector("#bankCount").textContent = `${banks.length} 个`;
  bankFilter.innerHTML = `
    <option value="">全部题库</option>
    ${banks
      .map(
        (bank) =>
          `<option value="${escapeHtml(bank.id)}">${escapeHtml(bank.name)}</option>`,
      )
      .join("")}
  `;
  document.querySelector("#libraryCreateBank").innerHTML = banks
    .map(
      (bank) =>
        `<option value="${escapeHtml(bank.id)}">${escapeHtml(bank.name)}</option>`,
    )
    .join("");
  bankFilter.value = banks.some((bank) => bank.id === selectedBank)
    ? selectedBank
    : "";
}

function snapshotHint(snapshot) {
  if (snapshot.type === "single" || snapshot.type === "multiple") {
    return `${snapshot.options.length} 个选项`;
  }
  if (snapshot.type === "text") {
    return `${snapshot.validation.minLength}-${snapshot.validation.maxLength} 字符`;
  }
  const minimum = snapshot.validation.min ?? "不限";
  const maximum = snapshot.validation.max ?? "不限";
  return `${minimum} 至 ${maximum}${snapshot.validation.integer ? " · 仅整数" : ""}`;
}

function questionCard(question) {
  const version = question.currentVersion;
  return `
    <article class="library-question-card" data-question-id="${escapeHtml(question.id)}" tabindex="0">
      <div class="card-top">
        <span class="type-badge">${typeLabel(question.currentVersion.snapshot.type)}</span>
        <span class="version-badge">v${version.versionNumber}</span>
      </div>
      <h3>${escapeHtml(version.snapshot.title)}</h3>
      <p>${escapeHtml(snapshotHint(version.snapshot))}</p>
      <div class="library-card-meta">
        <span>${escapeHtml(question.bankName)}</span>
        <span>${question.isShared ? `共享自 ${escapeHtml(question.ownerUsername)}` : "我创建的"}</span>
      </div>
      <div class="library-card-footer">
        <span class="small muted">${formatDate(question.updatedAt)}</span>
        <span class="small">查看版本与统计 →</span>
      </div>
    </article>
  `;
}

function renderQuestions() {
  const search = searchInput.value.trim().toLocaleLowerCase("zh-CN");
  const visible = questions.filter((question) => {
    if (!search) return true;
    return question.currentVersion.snapshot.title
      .toLocaleLowerCase("zh-CN")
      .includes(search);
  });
  questionList.innerHTML = visible.map(questionCard).join("");
  questionList.hidden = visible.length === 0;
  questionEmpty.hidden = visible.length !== 0;
}

async function loadBanks() {
  banks = await api("/api/question-banks");
  renderBanks();
}

async function loadQuestions() {
  const params = new URLSearchParams({
    scope: scopeFilter.value || "all",
  });
  if (bankFilter.value) params.set("bankId", bankFilter.value);
  questions = await api(`/api/library-questions?${params}`);
  renderQuestions();
}

async function refreshAll() {
  await loadBanks();
  await loadQuestions();
}

function validationFields(type, prefix, snapshot = {}) {
  if (type === "single" || type === "multiple") {
    const validation = snapshot.validation || {};
    return `
      <div class="field">
        <label for="${prefix}Options">选项，每行一个</label>
        <textarea id="${prefix}Options" required>${escapeHtml((snapshot.options || []).map((option) => option.label).join("\n"))}</textarea>
      </div>
      ${
        type === "multiple"
          ? `
            <div class="two-columns">
              <div class="field">
                <label for="${prefix}MinSelections">最少选择</label>
                <input id="${prefix}MinSelections" type="number" min="0" value="${validation.minSelections ?? 0}">
              </div>
              <div class="field">
                <label for="${prefix}MaxSelections">最多选择</label>
                <input id="${prefix}MaxSelections" type="number" min="1" value="${validation.maxSelections ?? 2}">
              </div>
            </div>
          `
          : ""
      }
    `;
  }
  if (type === "text") {
    const validation = snapshot.validation || {};
    return `
      <div class="two-columns">
        <div class="field">
          <label for="${prefix}MinLength">最少字符</label>
          <input id="${prefix}MinLength" type="number" min="0" value="${validation.minLength ?? 0}">
        </div>
        <div class="field">
          <label for="${prefix}MaxLength">最多字符</label>
          <input id="${prefix}MaxLength" type="number" min="1" value="${validation.maxLength ?? 500}">
        </div>
      </div>
    `;
  }
  const validation = snapshot.validation || {};
  return `
    <div class="two-columns">
      <div class="field">
        <label for="${prefix}Minimum">最小值</label>
        <input id="${prefix}Minimum" type="number" step="any" value="${validation.min ?? ""}" placeholder="不限">
      </div>
      <div class="field">
        <label for="${prefix}Maximum">最大值</label>
        <input id="${prefix}Maximum" type="number" step="any" value="${validation.max ?? ""}" placeholder="不限">
      </div>
    </div>
    <label class="checkbox-row">
      <input id="${prefix}Integer" type="checkbox" ${validation.integer ? "checked" : ""}>
      <span>只允许整数</span>
    </label>
  `;
}

function renderCreateTypeFields() {
  const type = document.querySelector("#libraryCreateType").value;
  document.querySelector("#libraryCreateTypeFields").innerHTML =
    validationFields(type, "libraryCreate", {
      options:
        type === "single" || type === "multiple"
          ? [{ label: "选项 1" }, { label: "选项 2" }]
          : [],
    });
}

function numOrNull(value) {
  return value === "" ? null : Number(value);
}

function optionsFromLines(text, baseOptions = []) {
  return text
    .split(/\r?\n/)
    .map((label) => label.trim())
    .filter(Boolean)
    .map((label, index) => ({
      id: baseOptions[index]?.id || randomId("o_"),
      label,
    }));
}

function snapshotFromFields(type, prefix, baseOptions = []) {
  const required = document.querySelector(`#${prefix}Required`).checked;
  const titleElement =
    document.querySelector(`input#${prefix}Title`) ||
    document.querySelector(`input#${prefix}TitleInput`);
  const title = titleElement?.value.trim() ?? "";
  if (type === "single" || type === "multiple") {
    const options = optionsFromLines(
      document.querySelector(`#${prefix}Options`).value,
      baseOptions,
    );
    return {
      title,
      type,
      required,
      options,
      validation:
        type === "multiple"
          ? {
              minSelections: Number(
                document.querySelector(`#${prefix}MinSelections`).value,
              ),
              maxSelections: Number(
                document.querySelector(`#${prefix}MaxSelections`).value,
              ),
            }
          : {},
    };
  }
  if (type === "text") {
    return {
      title,
      type,
      required,
      options: [],
      validation: {
        minLength: Number(
          document.querySelector(`#${prefix}MinLength`).value,
        ),
        maxLength: Number(
          document.querySelector(`#${prefix}MaxLength`).value,
        ),
      },
    };
  }
  return {
    title,
    type,
    required,
    options: [],
    validation: {
      min: numOrNull(document.querySelector(`#${prefix}Minimum`).value),
      max: numOrNull(document.querySelector(`#${prefix}Maximum`).value),
      integer: document.querySelector(`#${prefix}Integer`).checked,
    },
  };
}

function openCreateDialog() {
  createForm.reset();
  setError(createError);
  document.querySelector("#libraryCreateRequired").checked = true;
  const selectedBank = bankFilter.value || banks[0]?.id;
  if (selectedBank) {
    document.querySelector("#libraryCreateBank").value = selectedBank;
  }
  renderCreateTypeFields();
  createDialog.hidden = false;
  document.querySelector("#libraryCreateTitleInput").focus();
}

function closeCreateDialog() {
  createDialog.hidden = true;
}

function versionHistory(versions) {
  return versions
    .slice()
    .reverse()
    .map(
      (version) => `
        <div class="version-row">
          <div>
            <strong>v${version.versionNumber}</strong>
            <span class="small muted">${escapeHtml(version.changeSummary || "未填写版本说明")}</span>
            <div class="version-lineage">
              ${version.parentVersionId ? "来自上一版本" : "原始版本"}
              ${version.restoredFromVersionId ? " · 由历史版本恢复" : ""}
              · ${formatDate(version.createdAt)}
            </div>
          </div>
          ${
            selectedDetail.question.isOwner && version.versionNumber !== selectedDetail.question.currentVersion.versionNumber
              ? `<button class="button secondary small" type="button" data-restore-version="${escapeHtml(version.id)}">恢复为新版本</button>`
              : version.versionNumber === selectedDetail.question.currentVersion.versionNumber
                ? '<span class="version-badge">当前</span>'
                : ""
          }
        </div>
      `,
    )
    .join("");
}

function usageList(usages) {
  if (!usages.length) {
    return '<p class="muted small">当前用户的问卷还没有使用这一版本族。</p>';
  }
  return `
    <div class="usage-list">
      ${usages
        .map(
          (usage) => `
            <a class="usage-row" href="/stats/${escapeHtml(usage.surveyId)}">
              <span>
                <strong>${escapeHtml(usage.surveyTitle)}</strong>
                <small>使用题库 v${usage.libraryVersionNumber || "—"}</small>
              </span>
              <span>查看统计 →</span>
            </a>
          `,
        )
        .join("")}
    </div>
  `;
}

function crossSurveyStats(stats) {
  let body = "";
  if (stats.type === "single" || stats.type === "multiple") {
    body = stats.options
      .map(
        (option) => `
          <div class="bar-row">
            <span>${escapeHtml(option.label)}</span>
            <progress class="bar-track" max="100" value="${option.percentage}"></progress>
            <span class="bar-value">${option.count} 次 · ${option.percentage}%</span>
          </div>
        `,
      )
      .join("");
  } else if (stats.type === "number") {
    body = `
      <div class="numeric-summary">
        <div><span class="small muted">平均值</span><strong>${stats.numeric.average ?? "—"}</strong></div>
        <div><span class="small muted">最小值</span><strong>${stats.numeric.min ?? "—"}</strong></div>
        <div><span class="small muted">最大值</span><strong>${stats.numeric.max ?? "—"}</strong></div>
      </div>
    `;
  } else if (stats.textValues.length) {
    body = `
      <div class="text-answers">
        ${stats.textValues
          .map(
            (value, index) =>
              `<div class="text-answer"><strong class="small muted">回答 ${index + 1}</strong><br>${escapeHtml(value)}</div>`,
          )
          .join("")}
      </div>
    `;
  } else {
    body = '<p class="muted">暂时没有回答。</p>';
  }
  return `
    <div class="metrics-grid compact-metrics">
      <div class="metric"><div class="metric-label">使用问卷</div><div class="metric-value">${stats.surveyUsageCount}</div></div>
      <div class="metric"><div class="metric-label">提交</div><div class="metric-value">${stats.totalSubmissions}</div></div>
      <div class="metric"><div class="metric-label">回答</div><div class="metric-value">${stats.answeredCount}</div></div>
    </div>
    <p class="small muted">包含版本：${stats.versionsIncluded.length ? stats.versionsIncluded.map((version) => `v${version}`).join("、") : "暂无"}。${escapeHtml(stats.scope)}。</p>
    ${body}
  `;
}

function renderDetail() {
  const { question, versions, usages, stats } = selectedDetail;
  const snapshot = question.currentVersion.snapshot;
  const ownerEditor = question.isOwner
    ? `
      <form class="form-stack detail-editor" id="libraryVersionForm">
        <div class="section-title compact-title">
          <h3>创建新版本</h3>
          <span class="small muted">不会修改已有问卷和旧版本</span>
        </div>
        <div class="field">
          <label for="versionTitle">题目文本</label>
          <input id="versionTitle" maxlength="300" value="${escapeHtml(snapshot.title)}" required>
        </div>
        <label class="checkbox-row">
          <input id="versionRequired" type="checkbox" ${snapshot.required ? "checked" : ""}>
          <span>默认必答</span>
        </label>
        ${validationFields(snapshot.type, "version", snapshot)}
        <div class="field">
          <label for="versionSummary">本次修改说明</label>
          <input id="versionSummary" maxlength="300" placeholder="说明为什么创建新版本">
        </div>
        <button class="button" type="submit">保存为新版本</button>
      </form>
    `
    : '<p class="notice">这是其他用户共享给你的题目。你可以加入自己的问卷，但不能修改版本或恢复历史。</p>';

  detailBody.innerHTML = `
    <div class="detail-summary">
      <div>
        <p class="eyebrow">${typeLabel(snapshot.type)} · v${question.currentVersion.versionNumber}</p>
        <h3>${escapeHtml(snapshot.title)}</h3>
        <p class="muted">${escapeHtml(question.bankName)} · ${question.isShared ? `共享自 ${escapeHtml(question.ownerUsername)}` : "我创建的"}</p>
      </div>
      <span class="version-badge">${question.sharedWithCount} 人共享</span>
    </div>
    <div class="detail-actions">
      <a class="button secondary small" href="/">去问卷编辑器使用</a>
    </div>
    ${
      question.isOwner
        ? `
          <form class="share-form" id="shareQuestionForm">
            <div class="field">
              <label for="shareUsername">共享给用户名</label>
              <input id="shareUsername" maxlength="30" placeholder="同事的账号">
            </div>
            <button class="button secondary small" type="submit">共享</button>
          </form>
        `
        : ""
    }
    ${ownerEditor}
    <section>
      <div class="section-title compact-title">
        <h3>版本历史</h3>
        <span class="small muted">${versions.length} 个版本</span>
      </div>
      <div class="version-list">${versionHistory(versions)}</div>
    </section>
    <section>
      <div class="section-title compact-title">
        <h3>使用位置</h3>
        <span class="small muted">${usages.totalUsages} 处</span>
      </div>
      ${usageList(usages.usages)}
    </section>
    <section>
      <div class="section-title compact-title">
        <h3>跨问卷统计</h3>
        <span class="small muted">仅本人问卷</span>
      </div>
      ${crossSurveyStats(stats)}
    </section>
  `;
  bindDetailActions();
}

function bindDetailActions() {
  const form = document.querySelector("#libraryVersionForm");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const snapshot = snapshotFromFields(
        selectedDetail.question.currentVersion.snapshot.type,
        "version",
        selectedDetail.question.currentVersion.snapshot.options,
      );
      try {
        await api(
          `/api/library-questions/${selectedDetail.question.id}/versions`,
          {
            method: "POST",
            body: {
              baseVersionId:
                selectedDetail.question.currentVersion.id,
              snapshot,
              changeSummary:
                document.querySelector("#versionSummary").value,
            },
          },
        );
        toast("新版本已保存，已有问卷未受影响");
        await openDetail(selectedDetail.question.id);
        await loadQuestions();
      } catch (error) {
        setError(detailError, error.message);
      }
    });
  }
  const shareForm = document.querySelector("#shareQuestionForm");
  if (shareForm) {
    shareForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(
          `/api/library-questions/${selectedDetail.question.id}/share`,
          {
            method: "POST",
            body: {
              username: document.querySelector("#shareUsername").value,
            },
          },
        );
        toast("题目已共享给该用户");
        await openDetail(selectedDetail.question.id);
      } catch (error) {
        setError(detailError, error.message);
      }
    });
  }
  document.querySelectorAll("[data-restore-version]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api(
          `/api/library-questions/${selectedDetail.question.id}/restore`,
          {
            method: "POST",
            body: { versionId: button.dataset.restoreVersion },
          },
        );
        toast("历史内容已恢复为一个新版本");
        await openDetail(selectedDetail.question.id);
        await loadQuestions();
      } catch (error) {
        setError(detailError, error.message);
      }
    });
  });
}

async function openDetail(questionId) {
  setError(detailError);
  detailDialog.hidden = false;
  detailBody.innerHTML = '<div class="loading">正在读取版本和统计…</div>';
  try {
    const [detail, usages, stats] = await Promise.all([
      api(`/api/library-questions/${questionId}`),
      api(`/api/library-questions/${questionId}/usages`),
      api(`/api/library-questions/${questionId}/stats`),
    ]);
    selectedDetail = { ...detail, usages, stats };
    document.querySelector("#libraryQuestionDialogTitle").textContent =
      detail.question.currentVersion.snapshot.title;
    document.querySelector("#libraryQuestionKicker").textContent =
      `${typeLabel(detail.question.currentVersion.snapshot.type)} · ${detail.question.currentVersion.snapshot.title}`;
    renderDetail();
  } catch (error) {
    detailBody.innerHTML = "";
    setError(detailError, error.message);
  }
}

function closeDetail() {
  detailDialog.hidden = true;
  selectedDetail = null;
}

async function initialize() {
  try {
    const me = await api("/api/auth/me");
    setupUserBar(me.user);
    await refreshAll();
    loading.hidden = true;
    content.hidden = false;
  } catch (error) {
    loading.hidden = true;
    if (error.status === 401) {
      window.location.assign(
        `/login?next=${encodeURIComponent(window.location.pathname)}`,
      );
      return;
    }
    message.hidden = false;
    message.innerHTML = `<div><h2>无法打开题目库</h2><p>${escapeHtml(error.message)}</p></div>`;
  }
}

bankList.addEventListener("click", (event) => {
  const item = event.target.closest("[data-bank-id]");
  if (!item) return;
  bankFilter.value =
    bankFilter.value === item.dataset.bankId ? "" : item.dataset.bankId;
  renderBanks();
  loadQuestions().catch((error) => toast(error.message, "error"));
});
questionList.addEventListener("click", (event) => {
  const card = event.target.closest("[data-question-id]");
  if (card) openDetail(card.dataset.questionId);
});
questionList.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const card = event.target.closest("[data-question-id]");
  if (card) {
    event.preventDefault();
    openDetail(card.dataset.questionId);
  }
});
bankFilter.addEventListener("change", () => {
  renderBanks();
  loadQuestions().catch((error) => toast(error.message, "error"));
});
scopeFilter.addEventListener("change", () => {
  loadQuestions().catch((error) => toast(error.message, "error"));
});
searchInput.addEventListener("input", renderQuestions);
document
  .querySelector("#newLibraryQuestionButton")
  .addEventListener("click", openCreateDialog);
document
  .querySelector("#closeLibraryCreateDialog")
  .addEventListener("click", closeCreateDialog);
document.querySelector("#cancelLibraryCreate").addEventListener("click", closeCreateDialog);
document
  .querySelector("#libraryCreateType")
  .addEventListener("change", renderCreateTypeFields);
document
  .querySelector("#closeLibraryQuestionDialog")
  .addEventListener("click", closeDetail);
createDialog.addEventListener("click", (event) => {
  if (event.target === createDialog) closeCreateDialog();
});
detailDialog.addEventListener("click", (event) => {
  if (event.target === detailDialog) closeDetail();
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!createDialog.hidden) closeCreateDialog();
  if (!detailDialog.hidden) closeDetail();
});

document.querySelector("#bankForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  setError(document.querySelector("#bankError"));
  try {
    await api("/api/question-banks", {
      method: "POST",
      body: {
        name: document.querySelector("#bankName").value,
        description: document.querySelector("#bankDescription").value,
      },
    });
    event.target.reset();
    toast("题库已创建");
    await loadBanks();
  } catch (error) {
    setError(document.querySelector("#bankError"), error.message);
  }
});

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setError(createError);
  const type = document.querySelector("#libraryCreateType").value;
  const snapshot = snapshotFromFields(type, "libraryCreate");
  try {
    await api("/api/library-questions", {
      method: "POST",
      body: {
        bankId: document.querySelector("#libraryCreateBank").value,
        question: snapshot,
        changeSummary: document.querySelector("#libraryChangeSummary").value,
      },
    });
    closeCreateDialog();
    toast("题目已保存到题库");
    await refreshAll();
  } catch (error) {
    setError(createError, error.message);
  }
});

initialize();
