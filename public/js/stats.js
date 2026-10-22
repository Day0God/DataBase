import {
  api,
  escapeHtml,
  formatDate,
  setupUserBar,
  toast,
  typeLabel,
} from "./api.js";

const surveyId = window.location.pathname.split("/").filter(Boolean).pop();
const loading = document.querySelector("#statsLoading");
const message = document.querySelector("#statsMessage");
const content = document.querySelector("#statsContent");
const statList = document.querySelector("#statList");
const statsEmpty = document.querySelector("#statsEmpty");
const questionFilter = document.querySelector("#questionFilter");
let statistics = null;

function metricNumber(value) {
  return Number(value).toLocaleString("zh-CN");
}

function renderChoice(question) {
  return `
    <div class="stat-list">
      ${question.options
        .map(
          (option) => `
            <div class="bar-row">
              <span>${escapeHtml(option.label)}</span>
              <progress class="bar-track" max="100" value="${option.percentage}" aria-label="${escapeHtml(option.label)}：${option.percentage}%"></progress>
              <span class="bar-value">${option.count} 次 · ${option.percentage}%</span>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderText(question) {
  if (!question.textValues.length) {
    return '<p class="muted">本题暂无填写内容。</p>';
  }
  return `
    <div class="text-answers">
      ${question.textValues
        .map(
          (value, index) => `
            <div class="text-answer"><strong class="small muted">回答 ${index + 1}</strong><br>${escapeHtml(value)}</div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderNumber(question) {
  const data = question.numeric;
  return `
    <div class="numeric-summary">
      <div><span class="small muted">平均值</span><strong>${data.average ?? "—"}</strong></div>
      <div><span class="small muted">最小值</span><strong>${data.min ?? "—"}</strong></div>
      <div><span class="small muted">最大值</span><strong>${data.max ?? "—"}</strong></div>
    </div>
    <p class="small muted">全部数值：${data.values.length ? escapeHtml(data.values.join("、")) : "暂无"}</p>
  `;
}

function renderQuestion(question) {
  let body = "";
  if (question.type === "single" || question.type === "multiple") {
    body = renderChoice(question);
  } else if (question.type === "number") {
    body = renderNumber(question);
  } else {
    body = renderText(question);
  }
  return `
    <article class="stat-card">
      <div class="stat-heading">
        <div>
          <p class="eyebrow">第 ${question.order + 1} 题 · ${typeLabel(question.type)}</p>
          <h3>${escapeHtml(question.title)}</h3>
        </div>
        <span class="answer-count">${question.answeredCount} 人回答</span>
      </div>
      ${body}
    </article>
  `;
}

function renderQuestionList() {
  const filter = questionFilter.value;
  const visible =
    filter === "all"
      ? statistics.questions
      : statistics.questions.filter((question) => question.id === filter);
  statList.innerHTML = visible.map(renderQuestion).join("");
  statsEmpty.hidden =
    statistics.totalSubmissions !== 0 || statistics.questions.length === 0;
  if (statistics.totalSubmissions === 0 && statistics.questions.length > 0) {
    statList.innerHTML = "";
  }
}

function render() {
  document.querySelector("#statsTitle").textContent = statistics.survey.title;
  document.querySelector("#statsSubtitle").textContent =
    statistics.survey.description || "查看每一道题的实时汇总结果";
  document.querySelector("#totalSubmissions").textContent = metricNumber(
    statistics.totalSubmissions,
  );
  document.querySelector("#questionCount").textContent = metricNumber(
    statistics.questions.length,
  );
  document.querySelector("#collectionMode").textContent =
    statistics.survey.allowAnonymous ? "匿名" : "实名";
  document.querySelector("#generatedAt").textContent =
    `统计生成于 ${formatDate(statistics.generatedAt)}`;
  document.querySelector("#backBuilder").href = `/builder/${surveyId}`;
  questionFilter.innerHTML = `
    <option value="all">整份问卷</option>
    ${statistics.questions
      .map(
        (question) => `
          <option value="${escapeHtml(question.id)}">第 ${question.order + 1} 题 · ${escapeHtml(question.title.slice(0, 30))}</option>
        `,
      )
      .join("")}
  `;
  renderQuestionList();
}

async function load() {
  loading.hidden = false;
  content.hidden = true;
  message.hidden = true;
  try {
    statistics = await api(`/api/surveys/${surveyId}/stats`);
    loading.hidden = true;
    content.hidden = false;
    render();
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
        <h2>无法读取统计</h2>
        <p>${escapeHtml(error.message)}</p>
        <a class="button secondary" href="/">返回我的问卷</a>
      </div>
    `;
  }
}

questionFilter.addEventListener("change", renderQuestionList);
document.querySelector("#refreshStats").addEventListener("click", async () => {
  await load();
  toast("统计已刷新");
});

async function initialize() {
  const me = await api("/api/auth/me").catch((error) => {
    if (error.status === 401) {
      window.location.assign(
        `/login?next=${encodeURIComponent(window.location.pathname)}`,
      );
    } else {
      toast(error.message, "error");
    }
    return null;
  });
  if (!me) return;
  setupUserBar(me.user);
  await load();
}

initialize();
