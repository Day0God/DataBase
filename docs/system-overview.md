# 系统说明

## 1. 系统定位

MongoForm 是一个简化版在线问卷系统，覆盖从注册、创建问卷、配置题目、分发链接、填写提交到聚合统计的完整流程。项目使用 Python、Flask、MongoDB 和原生前端，不依赖关系数据库或现成问卷框架。

系统面向两类操作：

- 注册用户管理自己创建的问卷，查看回答统计。
- 已登录用户通过 `/survey/<slug>` 链接填写其他用户发布的问卷。

## 2. 功能范围

| 模块 | 已实现功能 |
| --- | --- |
| 账号 | 注册、登录、退出、会话保持、注册时间显示 |
| 问卷管理 | 创建、编辑、发布、关闭、重新开放、截止时间 |
| 题目 | 单选、多选、文本填空、数字填空、默认必答 |
| 校验 | 必答、多选数量、文本长度、数字范围、整数 |
| 跳转 | 单选选项、多选包含选项、数字比较、第一条规则优先 |
| 填写 | 一次一题、动态路径、浏览器提示、服务端复核 |
| 重复控制 | 每人一次、允许多次、幂等提交 |
| 匿名 | 不在回答中保存用户 ID，使用 HMAC 去重键 |
| 统计 | 选项频数、百分比、文本列表、数字平均值/最小值/最大值 |
| 题目库 | 常用题目保存、命名题库、题目共享和版本选择 |
| 版本管理 | 不可变历史、父子关系、恢复旧版本和新版本并存 |
| 跨问卷统计 | 当前用户的多份问卷中同一题库题目统一汇总 |

## 3. 技术架构

```text
Browser
  ├─ 原生 HTML / CSS / JavaScript
  └─ 同源 JSON API
          │
          ▼
Flask application
  ├─ 认证与所有权检查
  ├─ 标题、题目和答案校验
  ├─ 跳转路径解释器
  ├─ 提交幂等与重复控制
  └─ MongoDB 聚合统计
          │
          ▼
MongoDB
  ├─ users
  ├─ sessions
  ├─ surveys
  ├─ questions
  ├─ submissions
  ├─ question_banks
  ├─ library_questions
  └─ library_question_versions
```

## 4. 页面与入口

| 页面 | 地址 | 主要操作 |
| --- | --- | --- |
| 登录/注册/问卷列表 | `/`、`/login`、`/register` | 管理账号和自己的问卷 |
| 问卷编辑器 | `/builder/<surveyId>` | 修改说明、题目、校验和跳转 |
| 问卷填写页 | `/survey/<slug>` | 登录后回答并提交 |
| 统计页 | `/stats/<surveyId>` | 查看整卷或指定题目统计 |
| 题目库 | `/library` | 保存、共享、查看版本与跨问卷统计 |

## 5. 数据存储原则

所有业务运行数据存储在 MongoDB：

- 用户和密码哈希。
- 登录会话和过期时间。
- 问卷配置与发布状态。
- 题目、选项、校验和跳转规则。
- 每次已完成的回答提交。
- 用户题库、共享关系、题目版本谱系和问卷内来源快照。

浏览器 Cookie 只保存随机会话令牌；原始令牌不在 MongoDB 明文保存，数据库中保存 SHA-256 哈希。

## 6. 运行方式

环境要求：

- Python 3.10 或更高版本。
- MongoDB 7 或更高版本。

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

启动 MongoDB 后运行：

```powershell
python server.py
```

默认访问地址：

```text
http://127.0.0.1:3000
```

可选的演示初始化：

```powershell
python seed.py
```

演示用户：

```text
用户名：demo
密码：Demo12345
```

## 7. 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `3000` | Web 服务端口 |
| `MONGODB_URI` | `mongodb://127.0.0.1:27017/dm_questionnaire` | 数据库连接 |
| `SESSION_DAYS` | `7` | 会话有效天数 |
| `RESPONDENT_SECRET` | 开发占位值 | 匿名去重键 HMAC 密钥 |
| `SECURE_COOKIES` | `false` | HTTPS 环境应设为 `true` |
| `COOKIE_NAME` | `dm_session` | 会话 Cookie 名称 |
| `FLASK_ENV` | 未设置 | 设为 `production` 时检查生产配置 |
| `FLASK_DEBUG` | `false` | 是否开启调试模式 |

详细启动说明见根目录 [README](../README.md)。

## 8. 文档导航

- [数据库设计](database-design.md)
- [API 说明](api.md)
- [关键逻辑](logic.md)
- [测试用例与结果](test-cases.md)
- [AI 使用日志](ai-usage-log.md)
- [项目完成报告](project-report.md)
- [第二阶段项目报告](phase2-project-report.md)
