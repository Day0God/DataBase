# 手工测试指南

本文档给出从零启动、运行自动化测试和手工验收两阶段功能的完整步骤。

## 1. 测试用例在哪里

| 内容 | 文件 |
| --- | --- |
| 校验与跳转单元测试 | `test/test_validation.py` |
| API、数据库、统计与题库集成测试 | `test/test_integration.py` |
| 详细测试步骤、输入和预期结果 | `docs/test-cases.md` |
| 第一阶段与第二阶段基础手工测试 | `docs/phase2-manual-test-record.md` |
| 8 题复杂问卷、多路径、重复填写与跨问卷统计 | `docs/phase2-rich-test-record.md` |
| 可重复生成的复杂测试数据 | `scripts/seed_rich_test_data.py` |
| 浏览器截图证据 | `docs/phase2-test-evidence/` |

当前自动化测试为 `test_validation.py` 中的 7 个方法和 `test_integration.py` 中的 10 个方法，共 17 项。

## 2. 准备环境

在 PowerShell 中进入项目目录：

```powershell
cd C:\Code\DMSystem\Project01
python -m pip install -r requirements.txt
```

需要 Python 3.10+ 和 MongoDB。若 MongoDB 未运行，可打开一个独立终端启动：

```powershell
New-Item -ItemType Directory -Force .data\mongodb
& "C:\Program Files\MongoDB\Server\8.3\bin\mongod.exe" --dbpath "$PWD\.data\mongodb" --port 27018
```

后续命令中的 MongoDB 端口要与实际实例一致。

## 3. 运行自动化测试

```powershell
$env:TEST_MONGODB_URI = "mongodb://127.0.0.1:27018"
python -m unittest discover -s test -v
```

预期最后两行：

```text
Ran 17 tests in ...
OK
```

测试会创建随机命名的独立数据库，结束后自动删除，不会清空业务数据库。

可以单独运行某一项，例如：

```powershell
$env:TEST_MONGODB_URI = "mongodb://127.0.0.1:27018"
python -m unittest test.test_integration.IntegrationTests.test_library_question_cross_survey_statistics -v
```

## 4. 准备手工测试数据

复杂测试脚本会删除并重建指定测试数据库。不要指向正式数据库。

```powershell
$env:RICH_TEST_MONGODB_URI = "mongodb://127.0.0.1:27018"
$env:RICH_TEST_DATABASE_NAME = "dm_rich_visual_check"
python scripts\seed_rich_test_data.py
```

脚本会输出问卷链接、题库题目 ID、测试账号和预期统计。启动应用：

```powershell
$env:MONGODB_URI = "mongodb://127.0.0.1:27018/dm_rich_visual_check"
$env:PORT = "3014"
python server.py
```

浏览器打开：

```text
http://127.0.0.1:3014/
```

测试账号：

| 用户名 | 密码 | 用途 |
| --- | --- | --- |
| `rich_owner` | `RichTest123` | 查看创建者统计和题库所有者功能 |
| `rich_student` | `RichTest123` | 重复填写复杂问卷和题库问卷 |
| `rich_teacher` | `RichTest123` | 另一种分支路径 |
| `rich_engineer` | `RichTest123` | 非学生分支和较高投入 |
| `rich_partner` | `RichTest123` | 接收共享题目 |

## 5. 第一阶段手工测试步骤

1. 在首页登录 `rich_owner`，点击“＋ 新建问卷”，填写标题和说明，点击“创建并编辑”。
2. 在编辑器中分别添加单选、多选、文本和数字题，检查新建题目默认必答。
3. 保存后点“发布问卷”，从分享区打开预览链接。
4. 不选择必答项直接点“下一题”，预期出现必答提示。
5. 文本题输入少于最小长度的内容，预期显示长度提示。
6. 数字题输入小数但勾选“只允许整数”时，预期显示整数提示。
7. 按条件选择分支，观察被跳过的必答题不要求填写。
8. 完成问卷并提交，预期出现“回答已提交”。
9. 打开统计页，核对总提交数、选项次数、文本列表和数字平均值。
10. 再打开同一问卷，若不允许多次填写，预期提示已经填写；若允许多次填写，应能再次提交并增加统计。
11. 关闭已有回答的问卷，预期题目锁定；点击“重新开放问卷”后状态恢复为收集中。

第一阶段预置演示数据也可运行：

```powershell
$env:MONGODB_URI = "mongodb://127.0.0.1:27018/dm_rich_visual_check"
python seed.py
```

预置账号为 `demo`，密码为 `Demo12345`。

## 6. 第二阶段题库步骤

1. 使用 `rich_owner` 登录，进入顶部“题目库”。
2. 在“综合测评题库”中确认 8 道可复用题目。
3. 打开“你每周投入多少小时？”，确认 v1、v2、v3 版本及其来源关系。
4. 打开“创建新版本”，修改标题或校验后保存，预期旧版本和已有问卷保持不变。
5. 在历史版本中点击“恢复为新版本”，预期生成新的当前版本，并显示恢复来源。
6. 在“共享给用户名”中填写 `rich_partner`，退出后登录该账号，预期能在题目库看到共享来源。
7. 共享账号打开题目详情，预期可查看版本，但没有编辑和恢复按钮。
8. 用 `rich_student` 打开“综合能力与体验调查（复杂版）”，连续提交两次不同路径。
9. 用所有者打开该问卷统计，预期提交数增加，各题回答人数仍按实际路径分别计算。
10. 回到题库打开“你每周投入”详情，检查“使用位置”和跨问卷统计。

## 7. 复杂统计核对

复杂测试脚本初始生成的主问卷有 6 份回答：

| 指标 | 预期 |
| --- | --- |
| 身份 | 学生 3、教师 2、工程师 1、研究人员 0 |
| 能力题回答人数 | 3 |
| 课程题回答人数 | 3 |
| 投入小时 | 平均 21.17、最小 8、最大 40 |
| 评分 | 平均 3、最小 1、最大 5 |
| 最满意回答人数 | 3 |
| 最需改进回答人数 | 6 |

脚本预置的题库跨问卷统计：

```text
使用位置：3
所有者问卷：2
提交：10
版本：v1、v2
平均值：17.2
最小值：5
最大值：40
```

如果按复杂测试记录继续用 `rich_student` 手工提交两次主问卷、两次跟踪问卷，主问卷会增加到 8 份，跨问卷统计会增加至 14 份，跨问卷平均值变为 18.07。

## 8. 查看可视化证据

测试总览：

- `docs/phase2-test-evidence/overview.png`
- `docs/phase2-test-evidence/rich/overview-rich.png`

复杂问卷完整截图：

- `docs/phase2-test-evidence/rich/02-complex-builder.png`
- `docs/phase2-test-evidence/rich/07-complex-stats-after-repeat.png`
- `docs/phase2-test-evidence/rich/08-cross-stats-after-repeat.png`

## 9. 手工测试注意事项

- 使用独立数据库和测试账号，不要把测试脚本指向正式数据。
- 多选百分比以该题实际回答人数为分母，因此多选选项百分比合计可能超过 100%。
- 跳转题不计入“被跳过题目”的回答人数。
- 跨问卷统计只汇总当前用户拥有的问卷；“使用位置”可以显示其他用户对共享题目的使用。
