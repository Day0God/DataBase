# MongoForm 在线问卷系统

一个完整可运行的简化版在线问卷系统。注册用户可以创建、编辑、发布和关闭问卷；登录用户可以通过 `/survey/<slug>` 链接填写；创建者可以查看整卷和逐题统计。第二阶段新增可复用题目库、题目共享、不可变版本历史和单题跨问卷统计。

系统使用 **Python + Flask + MongoDB 原生驱动 PyMongo**，没有使用任何现成问卷框架或关系数据库。

## 已实现功能

- 用户注册、登录、退出和持久化会话
- 问卷创建、查看、修改、发布、截止时间和关闭
- 单选、多选、文本填空、数字填空
- 必答、多选数量、文本长度、数字范围、整数校验
- 基于单选、多选和数字结果的数据驱动条件跳转
- 答案由服务端重新遍历和校验，浏览器校验不是唯一防线
- 匿名统计、每人一次、重复填写开关
- 提交幂等和唯一索引，避免双击或网络重试产生重复回答
- 单选/多选选项频数、填空题全部内容、数字平均值/最小值/最大值
- 整卷统计与指定题目筛选
- MongoDB JSON Schema 集合校验、TTL 会话索引和业务唯一索引
- 自动化单元测试和真实 MongoDB 集成测试
- 用户题库与题目版本管理
- 按用户名将题目共享给其他用户
- 问卷保存加入时的题目快照，题库改版不影响旧问卷
- 查看版本谱系、恢复历史版本和使用位置
- 当前用户拥有的问卷中，同一道题库题目的跨问卷统计

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3、Flask 3 |
| 数据库 | MongoDB 7/8、PyMongo 4 |
| 认证 | 随机会话令牌 + HttpOnly Cookie，会话保存在 MongoDB |
| 密码 | Werkzeug scrypt 哈希 |
| 前端 | 原生 HTML、CSS、JavaScript |
| 测试 | Python `unittest`、Flask Test Client、真实 MongoDB |

## 快速启动

### 1. 准备环境

需要：

- Python 3.10 或更高版本
- MongoDB 7 或更高版本

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果本机已安装 Flask 和 PyMongo，也可以直接使用当前 Python 环境。

### 2. 启动 MongoDB

如果 MongoDB 已作为 Windows 服务运行，可直接进入下一步。手动启动示例：

```powershell
New-Item -ItemType Directory -Force .data\mongodb
& "C:\Program Files\MongoDB\Server\8.3\bin\mongod.exe" --dbpath "$PWD\.data\mongodb"
```

默认连接地址是：

```text
mongodb://127.0.0.1:27017/dm_questionnaire
```

可通过 `MONGODB_URI` 修改。

### 3. 初始化演示数据（可选）

```powershell
python seed.py
```

演示账号：

```text
用户名：demo
密码：Demo12345
```

种子脚本会创建一份包含条件跳转的已发布问卷，并打印其 `/survey/...` 链接。

### 4. 启动服务

```powershell
python server.py
```

打开 [http://127.0.0.1:3000](http://127.0.0.1:3000)。

登录后打开 [http://127.0.0.1:3000/library](http://127.0.0.1:3000/library) 管理常用题目。

### 查看用户注册时间

登录后的“我的问卷”页面会在标题下方显示当前账号及注册时间。后端接口 `GET /api/auth/me` 也会返回 `createdAt`。

需要直接从数据库查看时：

```powershell
python scripts/user_info.py <用户名>
python scripts/user_info.py
```

第一条命令查看指定用户，第二条命令列出全部用户的注册时间；脚本不会输出密码哈希。

修改端口：

```powershell
$env:PORT = "3010"
python server.py
```

## 配置

配置通过环境变量传入。可参考 [.env.example](.env.example)，项目不会自动加载 `.env`。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `3000` | Web 服务端口 |
| `MONGODB_URI` | `mongodb://127.0.0.1:27017/dm_questionnaire` | MongoDB 连接串 |
| `SESSION_DAYS` | `7` | 登录会话有效天数 |
| `RESPONDENT_SECRET` | 开发占位值 | 匿名参与者去重键的 HMAC 密钥 |
| `SECURE_COOKIES` | `false` | HTTPS 生产环境应设为 `true` |
| `COOKIE_NAME` | `dm_session` | 会话 Cookie 名称 |
| `FLASK_ENV` | 未设置 | 设为 `production` 时强制检查安全配置 |
| `FLASK_DEBUG` | `false` | 是否开启调试模式 |

生产环境示例：

```powershell
$env:FLASK_ENV = "production"
$env:RESPONDENT_SECRET = "请替换为至少32位随机字符串"
$env:SECURE_COOKIES = "true"
$env:MONGODB_URI = "mongodb://数据库地址/dm_questionnaire"
python server.py
```

## 运行测试

测试会创建随机命名的独立数据库并在结束后删除，不会修改业务数据库。

```powershell
$env:TEST_MONGODB_URI = "mongodb://127.0.0.1:27017"
python -m unittest discover -s test -v
```

预期结果：

```text
Ran 17 tests
OK
```

项目实测环境：

```text
Python 3.13.7
Flask 3.1.3
PyMongo 4.18.2
MongoDB 8.3
Node.js 24（仅用于前端 JavaScript 语法检查）
```

## 目录结构

```text
.
├─ app/
│  ├─ __init__.py        # Flask 应用工厂、安全响应头、页面路由
│  ├─ config.py          # 环境配置
│  ├─ errors.py          # 统一 API 错误
│  ├─ routes.py          # 认证、问卷、填写、统计 API
│  ├─ schema.py          # MongoDB JSON Schema、索引初始化
│  ├─ security.py        # 密码、会话和匿名参与者键
│  └─ validation.py      # 题目模型、答案校验和跳转解释器
├─ public/
│  ├─ index.html         # 登录/注册/问卷列表
│  ├─ builder.html       # 问卷编辑器
│  ├─ survey.html        # 一次一题填写页
│  ├─ stats.html         # 统计页
│  ├─ library.html       # 题库、版本、共享和跨问卷统计
│  ├─ css/styles.css
│  └─ js/
├─ test/
│  ├─ test_validation.py
│  └─ test_integration.py
├─ docs/
├─ seed.py
├─ server.py
└─ requirements.txt
```

## 关键业务限制

- 问卷发布后不能直接修改题目，必须先关闭。这样可避免正在填写的人看到前后不一致的题目。
- 已有回答的问卷不能再修改题目。历史回答中的题目 ID 和选项 ID 因此始终可解释。
- 跳转目标只能位于当前题目之后。该限制消除跳转环路和无法结束的问卷。
- 同一问卷内，跳转规则按数组顺序使用第一条命中的规则。
- 匿名问卷不保存 `respondentId`；仅保存不可逆 HMAC 去重键，用于账号维度的重复提交控制。
- 问卷标题、说明、截止时间和匿名/多次填写设置可以继续更新，不改变历史题目结构。
- 题库版本不可原地修改；修改或恢复历史都会生成新版本。
- 问卷只保存题库题目的独立快照。题库产生新版本后，已加入问卷的内容保持不变。
- 跨问卷统计只汇总当前用户拥有的问卷，不向共享者暴露其他用户的回答。

## 文档

- [系统说明](docs/system-overview.md)
- [系统与数据库设计](docs/database-design.md)
- [API 说明](docs/api.md)
- [关键业务逻辑](docs/logic.md)
- [测试用例与结果](docs/test-cases.md)
- [第一阶段目标逐项自查](docs/phase1-compliance-check.md)
- [项目完成报告](docs/project-report.md)
- [第二阶段项目报告](docs/phase2-project-report.md)
- [第二阶段最终报告源文件](docs/phase2-final-report.md)
- [第二阶段最终报告 PDF](2026_ECNU_PJ1_2_徐文杰.pdf)
- [第二阶段需求实现记录](docs/phase2-requirements-trace.md)
- [第一阶段与第二阶段可视化测试记录](docs/phase2-manual-test-record.md)
- [复杂问卷、题库与统计验收记录](docs/phase2-rich-test-record.md)
- [完整手工测试指南](docs/manual-test-guide.md)
- [AI 使用记录](docs/ai-usage-log.md)
- [提交清单](docs/submission-checklist.md)
