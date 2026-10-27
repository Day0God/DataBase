# 第一阶段与第二阶段可视化测试记录

测试日期：2026-10-26

测试地址：`http://127.0.0.1:3010`

测试数据库：`dm_visual_phase2_20261026`（独立测试数据库）

浏览器：ChatGPT 内置浏览器

## 1. 测试账号与数据

| 账号 | 用途 |
| --- | --- |
| `demo` | 第一阶段登录、填写、统计、关闭和重新开放 |
| `visual_owner` | 第二阶段题库、共享、版本和跨问卷统计所有者 |
| `visual_tester` | 共享题目接收者 |

演示问卷由 `seed.py` 创建，包含单选、多选、文本、数字四种题型及两级条件跳转。第二阶段问卷由浏览器界面创建。

## 2. 第一阶段手动测试

| 编号 | 操作 | 预期 | 结果 |
| --- | --- | --- | --- |
| M01 | 使用演示账号登录 | 显示账号、注册时间和问卷列表 | 通过 |
| M02 | 打开已发布问卷编辑器 | 题目及跳转控件全部禁用 | 通过 |
| M03 | 不选择单选答案直接继续 | 显示必答提示，停留在当前题 | 通过 |
| M04 | 文本输入单个字符 | 显示至少 2 个字符提示 | 通过 |
| M05 | 多选不选择直接继续 | 显示必答提示 | 通过 |
| M06 | 选择多选 1 至 2 项后继续 | 进入数字题 | 通过 |
| M07 | 数字输入 `20.5` | 显示只允许整数提示 | 通过 |
| M08 | 数字输入 `60` 后继续 | 跳过第 5 题，进入第 6 题 | 通过 |
| M09 | 填写建议并提交 | 显示“回答已提交”，统计不显示身份 | 通过 |
| M10 | 查看整卷统计 | 单选频数、多选频数、文本、数字均值正确，跳过题回答数为 0 | 通过 |
| M11 | 切换单题统计 | 只显示年龄题的均值、最小值、最大值 | 通过 |
| M12 | 关闭已有回答的问卷 | 状态变为已关闭，题目仍锁定 | 通过 |
| M13 | 重新开放问卷 | 状态恢复为收集中，回答数保留 | 通过 |
| M14 | 同一账号再次访问每人一次问卷 | 显示“这份问卷你已经填写过了” | 通过 |

## 3. 第二阶段手动测试

| 编号 | 操作 | 预期 | 结果 |
| --- | --- | --- | --- |
| M15 | 进入 `/library` | 自动显示“我的题库” | 通过 |
| M16 | 创建“课程题库” | 题库列表和数量立即刷新 | 通过 |
| M17 | 创建“你的年龄是？”数字题 | 生成逻辑题目和 v1 | 通过 |
| M18 | 修改标题和最大值为 100 | 生成 v2，v1 仍保留 | 通过 |
| M19 | 恢复 v1 | 生成 v3，显示“恢复自 v1” | 通过 |
| M20 | 共享给 `visual_tester` | 共享人数变为 1 | 通过 |
| M21 | 问卷 A 从题库选择 v1 并发布 | 显示“题库题目 · v1” | 通过 |
| M22 | 问卷 B 从题库选择 v2 并发布 | 显示“题库题目 · v2” | 通过 |
| M23 | 所有者回答 A、共享用户回答 B | 两份问卷分别提交成功 | 通过 |
| M24 | 共享用户查看题目详情 | 可看历史版本，但不能创建或恢复版本 | 通过 |
| M25 | 所有者查看使用位置 | 显示问卷 A 使用 v1、问卷 B 使用 v2 | 通过 |
| M26 | 所有者查看跨问卷统计 | 使用问卷 2、提交 2、回答 2，平均值 25、最小值 20、最大值 30 | 通过 |

## 4. 自动化回归

最终运行：

```text
Ran 17 tests in 4.272s
OK
```

覆盖第一阶段原有 13 项功能，以及共享权限、问卷快照隔离、版本关系、恢复语义、使用关系和跨问卷统计。

随后增加包含 8 道题、6 条预置路径、2 次浏览器重复提交和 14 份跨问卷回答的复杂验收。详细结果见 `docs/phase2-rich-test-record.md`。

## 5. 视觉证据

关键截图位于：

- `docs/phase2-test-evidence/01-dashboard.png`
- `docs/phase2-test-evidence/02-builder-locked.png`
- `docs/phase2-test-evidence/03-survey-stats.png`
- `docs/phase2-test-evidence/04-required-validation.png`
- `docs/phase2-test-evidence/05-jump-to-question-6.png`
- `docs/phase2-test-evidence/06-library.png`
- `docs/phase2-test-evidence/07-version-history.png`
- `docs/phase2-test-evidence/07-cross-survey-stats.png`
- `docs/phase2-test-evidence/08-survey-a-v1-snapshot.png`
- `docs/phase2-test-evidence/09-survey-b-v2-snapshot.png`
- `docs/phase2-test-evidence/08-shared-library.png`
- `docs/phase2-test-evidence/09-shared-readonly.png`
- `docs/phase2-test-evidence/10-duplicate-blocked.png`
- `docs/phase2-test-evidence/overview.png`

浏览器控制台最终检查无错误。

## 6. 结论

两个阶段的主要用户流程均已通过真实浏览器操作验证。第一阶段原有功能和第二阶段新增题库能力可以同时运行，旧问卷快照在题库版本升级和恢复后保持不变。
