export class ApiError extends Error {
  constructor(message, status = 0, code = "REQUEST_FAILED", details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function api(path, options = {}) {
  const init = {
    method: options.method || "GET",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  };
  if (options.body !== undefined) {
    init.method = options.method || "POST";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError("无法连接服务器，请检查网络或服务状态", 0, "NETWORK_ERROR");
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(
      "服务器返回了无法识别的内容",
      response.status,
      "INVALID_RESPONSE",
    );
  }
  if (!response.ok) {
    throw new ApiError(
      payload?.error?.message || "请求失败",
      response.status,
      payload?.error?.code || "REQUEST_FAILED",
      payload?.error?.details || null,
    );
  }
  return payload.data;
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function formatDate(value, fallback = "未设置") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatDateShort(value, fallback = "未设置") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function toLocalInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function fromLocalInput(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export const statusLabels = {
  draft: "草稿",
  published: "收集中",
  closed: "已关闭",
};

export function typeLabel(type) {
  return {
    single: "单选题",
    multiple: "多选题",
    text: "文本填空",
    number: "数字填空",
  }[type] || type;
}

export function toast(message, kind = "success") {
  const element = document.querySelector("#toast");
  if (!element) return;
  element.textContent = message;
  element.dataset.kind = kind;
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    element.hidden = true;
  }, 3200);
}

export function safeNextPath(value) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/";
}

export async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST", body: {} });
  } finally {
    window.location.assign("/login");
  }
}

export async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
    toast("链接已复制");
  } catch {
    window.prompt("请复制链接", value);
  }
}

export function randomId(prefix = "q_") {
  const bytes = crypto.getRandomValues(new Uint8Array(7));
  return prefix + Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function setupUserBar(user) {
  const name = document.querySelector("[data-user-name]");
  if (name) name.textContent = user.username;
  const logoutButton = document.querySelector("[data-logout]");
  if (logoutButton) logoutButton.addEventListener("click", logout);
}
