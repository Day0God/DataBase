# API 说明

## 1. 通用约定

- 基础地址：`http://127.0.0.1:3000/api`
- 请求和响应均使用 JSON。
- `POST`、`PUT`、`PATCH`、`DELETE` 必须声明 `Content-Type: application/json`。
- 登录状态通过 HttpOnly、SameSite=Lax Cookie `dm_session` 维持。
- 浏览器请求使用同源 Fetch，并携带 `credentials: same-origin`。
- 时间使用带时区的 ISO 8601 字符串。

成功响应：

```json
{
  "data": {}
}
```

失败响应：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "第 2 题：请输入整数",
    "details": {
      "questionId": "q_age000001"
    }
  }
}
```

常见 HTTP 状态：

| 状态 | 含义 |
| --- | --- |
| `200` | 查询或更新成功 |
| `201` | 账号、问卷或回答创建成功 |
| `401` | 未登录或账号密码错误 |
| `404` | 资源不存在，或当前用户无权访问 |
| `409` | 用户名重复、问卷已发布、回答重复 |
| `410` | 问卷未发布、已关闭或已截止 |
| `415` | 请求不是 JSON |
| `422` | 业务字段或答案校验失败 |

## 2. 健康检查

### `GET /api/health`

响应：

```json
{ "data": { "status": "ok" } }
```

## 3. 认证 API

### `POST /api/auth/register`

请求：

```json
{
  "username": "alice",
  "password": "Password123"
}
```

约束：

- 用户名 3–30 字符。
- 支持中文、字母、数字、下划线、短横线。
- 密码 8–72 字符。
- 用户名标准化后唯一。

成功：`201`，同时设置会话 Cookie。

```json
{
  "data": {
    "user": {
      "id": "671d...",
      "username": "alice",
      "createdAt": "2026-10-21T12:00:00+00:00"
    }
  }
}
```

### `POST /api/auth/login`

请求同注册。成功返回用户信息并设置会话 Cookie。

### `GET /api/auth/me`

返回当前登录用户。未登录返回 `401/AUTH_REQUIRED`。

### `POST /api/auth/logout`

删除当前 MongoDB 会话并清除 Cookie。请求体可为 `{}`。

## 4. 问卷管理 API

除公开填写接口外，问卷管理接口都要求登录。

### `GET /api/surveys`

返回当前用户创建的问卷列表，包括回答数：

```json
{
  "data": [
    {
      "id": "6720...",
      "title": "课程反馈",
      "description": "匿名收集意见",
      "slug": "randomSlug",
      "status": "published",
      "allowAnonymous": true,
      "allowMultipleResponses": false,
      "closesAt": "2026-11-01T12:00:00+00:00",
      "publishedAt": "2026-10-21T12:00:00+00:00",
      "closedAt": null,
      "createdAt": "2026-10-21T11:50:00+00:00",
      "updatedAt": "2026-10-21T12:00:00+00:00",
      "submissionCount": 12,
      "hasResponses": true,
      "publicPath": "/survey/randomSlug"
    }
  ]
}
```

### `POST /api/surveys`

请求：

```json
{
  "title": "课程反馈",
  "description": "匿名收集意见",
  "allowAnonymous": true,
  "allowMultipleResponses": false,
  "closesAt": null
}
```

创建后状态为 `draft`。

### `GET /api/surveys/:id`

返回当前用户拥有的问卷详情及题目。`submissionCount` 和 `hasResponses` 用于让编辑器判断题目是否已被回答锁定：

```json
{
  "data": {
    "survey": {
      "id": "6720...",
      "title": "课程反馈",
      "status": "closed",
      "submissionCount": 12,
      "hasResponses": true
    },
    "questions": []
  }
}
```

访问其他用户的问卷返回 `404`，避免泄露资源是否存在。

### `PATCH /api/surveys/:id`

可部分更新：

```json
{
  "title": "新的标题",
  "description": "新的说明",
  "allowAnonymous": false,
  "allowMultipleResponses": true,
  "closesAt": "2026-12-01T12:00:00+08:00"
}
```

传入 `"closesAt": null` 表示取消截止时间。

### `PUT /api/surveys/:id/questions`

整体保存题目数组。仅允许在问卷未发布且没有回答时执行。

```json
{
  "questions": [
    {
      "id": "q_route0001",
      "type": "single",
      "title": "你的身份是？",
      "required": true,
      "options": [
        { "id": "o_student001", "label": "学生" },
        { "id": "o_worker0001", "label": "在职人员" }
      ],
      "validation": {},
      "jumps": [
        {
          "condition": {
            "optionId": "o_worker0001"
          },
          "targetQuestionId": "q_goal000001"
        }
      ]
    },
    {
      "id": "q_goal000001",
      "type": "multiple",
      "title": "关注哪些能力？",
      "required": true,
      "options": [
        { "id": "o_skill00001", "label": "编程" },
        { "id": "o_skill00002", "label": "沟通" }
      ],
      "validation": {
        "minSelections": 1,
        "maxSelections": 2
      },
      "jumps": []
    }
  ]
}
```

文本题：

```json
{
  "id": "q_text00001",
  "type": "text",
  "title": "补充说明",
  "required": false,
  "options": [],
  "validation": {
    "minLength": 0,
    "maxLength": 500
  },
  "jumps": []
}
```

数字题：

```json
{
  "id": "q_age000001",
  "type": "number",
  "title": "年龄",
  "required": true,
  "options": [],
  "validation": {
    "min": 0,
    "max": 120,
    "integer": true
  },
  "jumps": [
    {
      "condition": {
        "operator": "gte",
        "value": 60
      },
      "targetQuestionId": "q_senior001"
    }
  ]
}
```

题目数组顺序就是显示顺序；服务端会重新生成 `order`。

### `POST /api/surveys/:id/publish`

要求至少一道题；状态变为 `published`，并清空 `closedAt`。若截止时间已过则返回 `422`。

### `POST /api/surveys/:id/close`

状态变为 `closed`，`closedAt` 设置为当前时间。

## 5. 填写 API

### `GET /api/public/surveys/:slug`

要求登录。仅返回已发布、未截止问卷的公开内容。

```json
{
  "data": {
    "id": "6720...",
    "title": "产品体验调查",
    "description": "约 1 分钟",
    "allowAnonymous": true,
    "allowMultipleResponses": false,
    "closesAt": "2026-11-01T12:00:00+00:00",
    "canRespond": true,
    "alreadySubmitted": false,
    "questions": []
  }
}
```

如果该账号已经提交且不允许重复填写，`canRespond` 为 `false`。

### `POST /api/public/surveys/:slug/submit`

请求：

```json
{
  "idempotencyKey": "84f1a2f8-0b16-4b46-bb9f-a8cbbe02987c",
  "answers": [
    { "questionId": "q_route0001", "value": "o_student001" },
    { "questionId": "q_age000001", "value": 20 },
    { "questionId": "q_feedback1", "value": "体验很好" }
  ]
}
```

答案规则：

- 单选值为选项 ID 字符串。
- 多选值为选项 ID 字符串数组。
- 文本值为字符串，服务端去除首尾空白。
- 数字值为 JSON 数值或可转换数字，最终保存为数字。
- 只能提交实际路径到达的非空题目。
- 跳过的必答题不需要提交。
- 未回答的可选题可不放入数组，也可以传空值。

成功：`201`

```json
{
  "data": {
    "submissionId": "6721...",
    "submittedAt": "2026-10-21T12:30:00+00:00"
  }
}
```

相同用户、相同 `idempotencyKey` 重试时返回 `200` 和原提交 ID，并标记：

```json
{
  "data": {
    "submissionId": "6721...",
    "submittedAt": "2026-10-21T12:30:00+00:00",
    "idempotentReplay": true
  }
}
```

## 6. 统计 API

### `GET /api/surveys/:id/stats`

仅问卷所有者可访问。

```json
{
  "data": {
    "survey": {},
    "totalSubmissions": 2,
    "generatedAt": "2026-10-21T12:35:00+00:00",
    "questions": [
      {
        "id": "q_route0001",
        "title": "你的身份是？",
        "type": "single",
        "order": 0,
        "answeredCount": 2,
        "options": [
          {
            "id": "o_student001",
            "label": "学生",
            "count": 1,
            "percentage": 50
          }
        ]
      },
      {
        "id": "q_age000001",
        "title": "年龄",
        "type": "number",
        "order": 1,
        "answeredCount": 2,
        "numeric": {
          "average": 23.5,
          "min": 20,
          "max": 27,
          "values": [20, 27]
        }
      },
      {
        "id": "q_feedback1",
        "title": "补充反馈",
        "type": "text",
        "order": 2,
        "answeredCount": 1,
        "textValues": ["体验很好"]
      }
    ]
  }
}
```

说明：

- 单选/多选百分比以该题实际回答人数为分母。
- 多选项的百分比可以合计超过 100%，因为一名填写者可选择多个选项。
- 被跳转规则跳过的题目 `answeredCount` 为 0，不计入该题统计。
- 当前前端支持“整份问卷”和“某一道题”筛选。

## 7. 第二阶段题目库 API

以下接口都要求登录。

### `GET /api/question-banks`

返回当前用户的题库。首次访问时自动创建“我的题库”。

### `POST /api/question-banks`

```json
{
  "name": "课程反馈常用题",
  "description": "可跨问卷复用"
}
```

### `PATCH /api/question-banks/:id`

更新题库名称或说明。当前用户必须是题库所有者。

### `GET /api/library-questions`

查询可访问的逻辑题目：

```text
/api/library-questions?scope=all
/api/library-questions?scope=own
/api/library-questions?scope=shared
/api/library-questions?bankId=<题库ID>
```

### `POST /api/library-questions`

```json
{
  "bankId": "6720...",
  "question": {
    "type": "number",
    "title": "你的年龄是？",
    "required": true,
    "validation": {
      "min": 0,
      "max": 120,
      "integer": true
    }
  },
  "changeSummary": "创建常用题"
}
```

创建逻辑题目和 v1 版本。

### `GET /api/library-questions/:id`

返回逻辑题目、当前版本和全部历史版本。版本包含：

- `versionNumber`
- `parentVersionId`
- `restoredFromVersionId`
- `snapshot`
- `changeSummary`

### `POST /api/library-questions/:id/versions`

创建新版本：

```json
{
  "baseVersionId": "6720...",
  "snapshot": {
    "title": "年龄（成年）",
    "type": "number",
    "required": true,
    "options": [],
    "validation": {
      "min": 18,
      "max": 120,
      "integer": true
    }
  },
  "changeSummary": "限制为成年人"
}
```

只有所有者可以创建版本。同一版本族不能修改题型。

### `POST /api/library-questions/:id/restore`

```json
{
  "versionId": "6720...",
  "changeSummary": "恢复旧版文字"
}
```

不会覆盖当前版本，而是生成一个后继版本，并记录 `restoredFromVersionId`。

### `POST /api/library-questions/:id/share`

```json
{
  "username": "colleague"
}
```

共享后，对方可以查看题目和版本，并将任一可访问版本加入自己的问卷；对方不能修改所有者题目。

### `GET /api/library-questions/:id/usages`

逻辑题目的所有者可以查看所有问卷中的使用位置和版本号；被共享用户只能查看自己拥有的问卷。

### `GET /api/library-questions/:id/stats`

汇总当前用户拥有的多份问卷中该题目的回答。可添加 `?versionId=<版本ID>` 只查看一个版本。

返回内容包括：

- `surveyUsageCount`
- `totalSubmissions`
- `answeredCount`
- `versionsIncluded`
- 与题型对应的 `options`、`textValues` 或 `numeric`

跨问卷统计不返回其他用户的问卷或回答数据。

### 问卷中的题库来源

`PUT /api/surveys/:id/questions` 的题目可以携带：

```json
{
  "libraryQuestionId": "6720...",
  "libraryVersionId": "6721...",
  "libraryVersionNumber": 2
}
```

服务端验证当前用户有访问权、版本属于逻辑题目，并验证题目内容与版本快照一致后才保存来源关系。问卷内仍保存完整题目快照。
