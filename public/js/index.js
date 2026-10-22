import {
  api,
  copyText,
  escapeHtml,
  formatDate,
  formatDateShort,
  safeNextPath,
  setupUserBar,
  statusLabels,
  toast,
} from "./api.js";

const authView = document.querySelector("#authView");
const dashboardView = document.querySelector("#dashboardView");
const memberActions = document.querySelector("#memberActions");
const guestActions = document.querySelector("#guestActions");
const loginForm = document.querySelector("#loginForm");
const registerForm = document.querySelector("#registerForm");
const loginTab = document.querySelector("#loginTab");
const registerTab = document.querySelector("#registerTab");
const loginError = document.querySelector("#loginError");
const registerError = document.querySelector("#registerError");
const createDialog = document.querySelector("#createDialog");
const createForm = document.querySelector("#createSurveyForm");
const createError = document.querySelector("#createError");
const surveyGrid = document.querySelector("#surveyGrid");
const surveyEmpty = document.querySelector("#surveyEmpty");
const dashboardLoading = document.querySelector("#dashboardLoading");

const params = new URLSearchParams(window.location.search);
const nextPath = safeNextPath(params.get("next"));
let currentUser = null;

function showAuth(mode = "login") {
  authView.hidden = false;
  dashboardView.hidden = true;
  memberActions.hidden = true;
  guestActions.hidden = false;
  switchAuthMode(mode);
}

function switchAuthMode(mode) {
  const registering = mode === "register";
  loginForm.hidden = registering;
  registerForm.hidden = !registering;
  loginTab.classList.toggle("active", !registering);
  registerTab.classList.toggle("active", registering);
  loginTab.setAttribute("aria-selected", String(!registering));
  registerTab.setAttribute("aria-selected", String(registering));
  history.replaceState(
    null,
    "",
    registering ? `/register${nextPath === "/" ? "" : `?next=${encodeURIComponent(nextPath)}`}` : window.location.pathname,
  );
}

function setFormError(element, message = "") {
  element.textContent = message;
  element.hidden = !message;
}

async function afterAuthentication(user) {
  currentUser = user;
  setupUserBar(user);
  document.querySelector("#dashboardUsername").textContent = user.username;
  const createdAt = document.querySelector("#dashboardCreatedAt");
  createdAt.dateTime = user.createdAt;
  createdAt.textContent = formatDate(user.createdAt, "时间未知");
  if (nextPath !== "/") {
    window.location.assign(nextPath);
    return;
  }
  authView.hidden = true;
  dashboardView.hidden = false;
  memberActions.hidden = false;
  guestActions.hidden = true;
  await loadDashboard();
}

async function attemptAuth(path, form, errorElement) {
  setFormError(errorElement);
  const submit = form.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    const data = new FormData(form);
    const result = await api(path, {
      method: "POST",
      body: {
        username: data.get("username"),
        password: data.get("password"),
      },
    });
    await afterAuthentication(result.user);
  } catch (error) {
    setFormError(errorElement, error.message);
  } finally {
    submit.disabled = false;
  }
}

function surveyCard(survey) {
  const publicUrl = `${window.location.origin}${survey.publicPath}`;
  return `
    <article class="survey-card">
      <div class="card-top">
        <span class="status-pill ${escapeHtml(survey.status)}">${statusLabels[survey.status]}</span>
        <span class="card-count">${survey.submissionCount}<small class="muted"> 份</small></span>
      </div>
      <h3>${escapeHtml(survey.title)}</h3>
      <p>${escapeHtml(survey.description || "未填写问卷说明")}</p>
      <div class="card-footer">
        <span class="small muted">${survey.closesAt ? `截止 ${formatDateShort(survey.closesAt)}` : "不限截止时间"}</span>
        <div class="card-links">
          <a href="/builder/${survey.id}">编辑</a>
          <a href="/stats/${survey.id}">统计</a>
          ${
            survey.status === "published"
              ? `<button class="button ghost small" type="button" data-copy-link="${escapeHtml(publicUrl)}">复制链接</button>`
              : ""
          }
        </div>
      </div>
    </article>
  `;
}

async function loadDashboard() {
  dashboardLoading.hidden = false;
  surveyGrid.hidden = true;
  surveyEmpty.hidden = true;
  try {
    const surveys = await api("/api/surveys");
    surveyGrid.innerHTML = surveys.map(surveyCard).join("");
    surveyGrid.hidden = surveys.length === 0;
    surveyEmpty.hidden = surveys.length !== 0;
  } catch (error) {
    if (error.status === 401) {
      showAuth();
      return;
    }
    toast(error.message, "error");
  } finally {
    dashboardLoading.hidden = true;
  }
}

function openCreateDialog() {
  createForm.reset();
  document.querySelector("#allowAnonymous").checked = true;
  setFormError(createError);
  createDialog.hidden = false;
  document.querySelector("#surveyTitle").focus();
}

function closeCreateDialog() {
  createDialog.hidden = true;
}

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  attemptAuth("/api/auth/login", loginForm, loginError);
});

registerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  attemptAuth("/api/auth/register", registerForm, registerError);
});

loginTab.addEventListener("click", () => switchAuthMode("login"));
registerTab.addEventListener("click", () => switchAuthMode("register"));
document.querySelector("#showLogin").addEventListener("click", () => switchAuthMode("login"));
document.querySelector("#showRegister").addEventListener("click", () => switchAuthMode("register"));
document.querySelector("#newSurveyButton").addEventListener("click", openCreateDialog);
document.querySelector("#emptyCreateButton").addEventListener("click", openCreateDialog);
document.querySelector("#closeCreateDialog").addEventListener("click", closeCreateDialog);
document.querySelector("#cancelCreate").addEventListener("click", closeCreateDialog);
createDialog.addEventListener("click", (event) => {
  if (event.target === createDialog) closeCreateDialog();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !createDialog.hidden) closeCreateDialog();
});

surveyGrid.addEventListener("click", (event) => {
  const button = event.target.closest("[data-copy-link]");
  if (button) copyText(button.dataset.copyLink);
});

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setFormError(createError);
  const submit = createForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    const data = new FormData(createForm);
    const survey = await api("/api/surveys", {
      method: "POST",
      body: {
        title: data.get("title"),
        description: data.get("description"),
        allowAnonymous: data.get("allowAnonymous") === "on",
        allowMultipleResponses: data.get("allowMultipleResponses") === "on",
      },
    });
    window.location.assign(`/builder/${survey.id}`);
  } catch (error) {
    setFormError(createError, error.message);
  } finally {
    submit.disabled = false;
  }
});

async function initialize() {
  if (params.get("mode") === "register") switchAuthMode("register");
  try {
    const result = await api("/api/auth/me");
    await afterAuthentication(result.user);
  } catch (error) {
    if (error.status !== 401) toast(error.message, "error");
    showAuth(params.get("mode") === "register" ? "register" : "login");
  }
}

initialize();
