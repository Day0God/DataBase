# 系统与 MongoDB 数据库设计

## 1. 系统目标与总体结构

系统围绕四类核心对象组织：

1. **账号**：谁可以创建问卷、登录后填写。
2. **问卷**：标题、说明、状态、截止时间、匿名和重复填写策略。
3. **题目**：题型、选项、校验约束和条件跳转规则。
4. **回答**：一次完整提交中的答案集合，以及统计所需时间和参与者去重信息。

```text
Browser
  │
  ├─ HTML / CSS / 原生 JavaScript
  │
  ▼
Flask API
  ├─ Session/Auth
  ├─ Question validator
  ├─ Server-side jump interpreter
  └─ Statistics aggregation
  │
  ▼
MongoDB
  ├─ users
  ├─ sessions
  ├─ surveys
  ├─ questions
  └─ submissions
```

前后端职责：

- 浏览器负责交互、即时提示和路径预览。
- Flask 对每次提交重新执行完整答案校验和跳转遍历。
- MongoDB 保存全部业务数据，并通过 Schema、唯一索引和 TTL 索引维护基础完整性。
- 统计直接在 `submissions.answers` 上使用 MongoDB 聚合管道计算。

## 2. 集合设计

### `users`

```javascript
{
  _id: ObjectId,
  username: "alice",          // 展示名
  usernameKey: "alice",       // NFKC + casefold，用于唯一索引
  passwordHash: "scrypt...",
  createdAt: ISODate
}
```

设计说明：

- 同时保存展示名和标准化键，避免仅靠应用层大小写判断造成并发注册重复。
- 不保存明文密码或可逆加密密码。

索引：

```javascript
{ usernameKey: 1 } unique
```

### `sessions`

```javascript
{
  _id: ObjectId,
  tokenHash: "sha256...",
  userId: ObjectId,
  createdAt: ISODate,
  expiresAt: ISODate
}
```

浏览器 Cookie 中只保存随机原始令牌，数据库只保存其 SHA-256 哈希。这样即使数据库中的会话字段泄露，也不能直接拿来登录。

索引：

```javascript
{ tokenHash: 1 } unique
{ expiresAt: 1 } expireAfterSeconds: 0
```

TTL 索引会自动删除过期会话。

### `surveys`

```javascript
{
  _id: ObjectId,
  ownerId: ObjectId,
  title: "课程反馈",
  description: "匿名收集意见",
  slug: "random-url-safe-value",
  status: "draft" | "published" | "closed",
  allowAnonymous: true,
  allowMultipleResponses: false,
  closesAt: ISODate | null,
  publishedAt: ISODate | null,
  closedAt: ISODate | null,
  version: Number,
  createdAt: ISODate,
  updatedAt: ISODate
}
```

问卷元数据与题目分开，是为了让发布状态和配置可以独立更新，同时避免每次操作都把大题目数组重写。

索引：

```javascript
{ slug: 1 } unique
{ ownerId: 1, createdAt: -1 }
{ status: 1, closesAt: 1 }
```

### `questions`

```javascript
{
  _id: ObjectId,
  surveyId: ObjectId,
  id: "q_route0001",            // 问卷内稳定题目键
  type: "single" | "multiple" | "text" | "number",
  title: "你的身份是？",
  required: true,
  order: 0,
  options: [
    { id: "o_student001", label: "学生" },
    { id: "o_worker0001", label: "在职人员" }
  ],
  validation: {},
  jumps: [
    {
      condition: {
        operator: "option_is",
        optionId: "o_worker0001"
      },
      targetQuestionId: "q_goal000001"
    }
  ],
  createdAt: ISODate
}
```

题型对应的校验结构：

| 题型 | `validation` |
| --- | --- |
| 单选 | `{}`，选项本身必须合法 |
| 多选 | `{ minSelections, maxSelections }` |
| 文本 | `{ minLength, maxLength }` |
| 数字 | `{ min, max, integer }` |

索引：

```javascript
{ surveyId: 1, order: 1 } unique
```

`order` 唯一索引保证同一问卷内没有两个题目占用同一个顺序。

**为什么选项和跳转嵌入题目？**

- 选项、校验和跳转只属于当前题目。
- 一题最多 50 个选项、50 条跳转，整体远低于文档大小风险。
- 发布前题目通常整体读取与更新，拆成多个集合会增加无收益的连接操作。
- 跳转条件与题目选项需要在一次读取中完成一致性检查。

**为什么题目不嵌入问卷？**

- 题目有独立结构、顺序和索引需求。
- 发布前会整体替换题目集合，单独集合更容易删除、排序和校验。
- 统计时按题目逐一映射，不需要把整个问卷重复读取。

### `submissions`

```javascript
{
  _id: ObjectId,
  surveyId: ObjectId,
  respondentId: ObjectId | null,
  participantKey: "hmac-sha256...",
  anonymous: true,
  enforceOnce: false,
  idempotencyKey: "browser-uuid",
  answers: [
    { questionId: "q_route0001", value: "o_student001" },
    { questionId: "q_age000001", value: 20 }
  ],
  submittedAt: ISODate
}
```

**答案为什么嵌入一次回答？**

- 一次提交是一个天然的业务边界，必须作为整体保存。
- 统计通过 `$unwind: "$answers"` 直接分组，不需要跨集合拼接。
- 跳转路径只包含实际到达的题目，空数组形式和独立答案集合会让统计与完整性检查更复杂。
- 限制一题一次 `{ questionId, value }`，通过服务端遍历保证没有重复和未到达题目。

索引：

```javascript
{ surveyId: 1, submittedAt: -1 }
{ surveyId: 1, participantKey: 1 } unique, partialFilterExpression: { enforceOnce: true }
{ surveyId: 1, idempotencyKey: 1 } unique, partialFilterExpression: { idempotencyKey: { $type: "string" } }
```

第一个索引支持统计和时间查询；后两个索引分别防止并发重复回答和网络重试导致的重复写入。

## 3. 冗余与一致性

系统不把问卷标题、题目全文或创建者用户名复制到每条回答中。回答只保存稳定的 `questionId` 和选项 `optionId`，统计时通过题目集合解释。

为保护历史数据：

- 发布中的问卷不能改题。
- 已有回答的问卷不能改题。
- 当前阶段允许更新说明、截止时间和匿名策略，因为它们不改变答案含义。

这比把整份问卷重复放进每条回答更节省空间，也比无约束地修改题目更可靠。

## 4. 匿名与去重

匿名问卷的 `respondentId` 为 `null`，统计 API 不返回填写者身份。

但业务仍需要支持“同一账号只能填写一次”。系统额外保存：

```text
participantKey = HMAC-SHA256(RESPONDENT_SECRET, surveyId + userId)
```

它不能从回答文档直接反推出用户名，仅用于当前问卷维度的重复检查。严格来说，这属于**对业务界面匿名、保留技术去重键的伪匿名设计**，不应宣称对数据库管理员绝对不可关联。

## 5. 为什么适合 MongoDB

- 题目是带有可选题型结构的多态对象，不同题型具有不同校验字段。
- 跳转规则是长度可变的嵌套数组，直接与题目一起读写更自然。
- 一次回答的答案集合适合作为单个文档整体写入。
- 统计使用 `$unwind`、`$group`、`$facet` 非常直接。
- URL slug、所有者、状态、截止时间、参与者去重键都可以通过索引高效查询。
- JSON Schema 校验可以在数据库层拒绝明显错误的数据结构。

## 6. 为什么不是关系数据库模型

该需求不是不能映射为关系表，而是关系模型会引入不必要的拆分：

- 题目类型差异会导致宽表或额外约束表。
- 选项、条件、答案通常需要多张关联表。
- 读取一次问卷或回答需要多次 JOIN。
- 跳转规则可灵活扩展，关系模型需要更多枚举和关联结构。

MongoDB 将“题目 + 选项 + 条件”和“一次回答 + 答案列表”分别作为聚合边界，更贴合业务的读取方式与写入方式。同时，本设计没有把所有对象塞进一个超大文档，而是按生命周期和访问模式拆为五个集合。

## 7. 数据库结构定义位置

可执行的集合 JSON Schema、`collMod` 配置和全部索引位于：

- [`app/schema.py`](../app/schema.py)

应用启动时会幂等执行集合校验器和索引初始化。

## 8. 第二阶段题库与版本集合

第二阶段保留原有五个集合，并新增：

- `question_banks`：用户命名题库。
- `library_questions`：可复用的逻辑题目、所有者、当前版本和共享对象。
- `library_question_versions`：不可变版本快照与版本谱系。

### `question_banks`

```javascript
{
  _id: ObjectId,
  ownerId: ObjectId,
  name: "常用题目",
  nameKey: "常用题目",
  description: "",
  createdAt: ISODate,
  updatedAt: ISODate
}
```

唯一索引 `{ ownerId: 1, nameKey: 1 }` 防止同一用户创建同名题库。
`questions.libraryQuestionId + surveyId` 稀疏索引支持使用位置和跨问卷统计查询。

### `library_questions`

```javascript
{
  _id: ObjectId,
  bankId: ObjectId,
  ownerId: ObjectId,
  type: "single" | "multiple" | "text" | "number",
  currentVersionId: ObjectId,
  currentVersionNumber: 3,
  sharedWith: [ObjectId],
  createdAt: ISODate,
  updatedAt: ISODate
}
```

逻辑题目只保存稳定身份、当前版本和共享关系，具体题目内容位于版本文档。

索引：

```javascript
{ ownerId: 1, updatedAt: -1 }
{ bankId: 1, updatedAt: -1 }
{ sharedWith: 1, updatedAt: -1 }
```

### `library_question_versions`

```javascript
{
  _id: ObjectId,
  questionId: ObjectId,
  versionNumber: 3,
  parentVersionId: ObjectId | null,
  restoredFromVersionId: ObjectId | null,
  snapshot: {
    title: "你的年龄是？",
    type: "number",
    required: true,
    options: [],
    validation: { min: 0, max: 120, integer: true }
  },
  changeSummary: "恢复自 v1",
  createdBy: ObjectId,
  createdAt: ISODate
}
```

版本号唯一索引确保并发请求不能创建同一题目的重复版本。

### 问卷题目快照

`questions` 增加可选字段：

```javascript
{
  libraryQuestionId: ObjectId,
  libraryVersionId: ObjectId,
  libraryVersionNumber: Number,
  libraryOwnerId: ObjectId
}
```

问卷仍保存完整题目内容，不保存题库实时引用。新增字段只用于来源追溯和使用统计，因此第一阶段题目无需迁移，题库升级也不会改变旧问卷。
