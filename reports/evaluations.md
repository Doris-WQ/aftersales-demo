# 第五步：评测面板验收记录

## 已实现

- `src/evals/cases.json` 保存 E01–E15 原始输入和可观察判据，分布为正常 4、信息不足 3、高风险 4、无答案 4。
- 网页和 `python -m evals.run` 共用实际执行器：隔离 app、会话、订单 HTTP 工具和工单存储，
  逐条调用 `/api/chat`，转人工用例再通过工单接口查验。
- 后台任务有 queued/running/completed/failed 状态，重复启动复用运行中任务；完成后保存 JSON 和 Markdown。
  报告区分离线与真实模型，保留代码、政策和配置指纹；旧版本报告在网页提示重新运行。
- 页面展示实际进度、通过率、四类失败、逐条判据及实际响应；完整 JSON 默认折叠。
  历史失败复盘取自已有证据，不预填 E08 曾失败。

## 实际验证

- 完整 pytest：**206 passed**，含任务隔离、重启读取、重复运行、取消任务、模型执行错误计数、
  错误引用、虚构工单、高金额退款承诺及无依据支付答案的判定器反例。
  记录：`step5-tests.xml`。有一条已知 Starlette/httpx 弃用提示。
- Ruff 检查通过，29 个 Python 文件格式通过；未新增依赖。
- 首轮真实离线业务报告：`evaluations/4805e591102a4c55b478a46f12d34295.json`，15/15；原始记录保留。
- 最终 CLI 报告：`evaluations/523f45c11ad24eb39aa32dbce21ec370.json`，15/15，执行错误 0。
- 最终网页实际运行：`evaluations/fae0ea86221e48f0b855aae960b7e3df.json`，15/15，执行错误 0。
  代码指纹为 `095876aaca517709760cb57b65c2e58077b00000716380a8b640ae5aa41aa24c`。

## 浏览器验证

- 点击“跑评测”观察到实际 1/15、最终版本重跑 2/15 的执行进度；运行中按钮禁用。
- 展开 E08：handoff、P12、R1，未执行检索，工单通过接口查验；没有把规则引用伪装成检索命中。
- 展开 F-MONEY-001：真实的模糊金额识别失败、相同输入修复后回放、根因和修复说明可见。
- 评测后两轮聊天和两轮轨迹仍保留；选择第一轮可显示 P01，评测 15 条结果不受影响。
- 手机宽度 390px，文档宽度 375px，无横向溢出，评测工具栏换行，失败对照改为纵向。
- 实际停止服务后读取报告：显示查询错误，已有 15 条成绩和聊天保留；恢复服务后可读取持久化报告。
  未把请求错误转换成新的“通过”结果。

截图：`step5-evaluations-desktop.jpg`、`step5-evaluations-mobile.jpg`、
`step5-failure-comparison.jpg`、`step5-evaluations-disconnect.jpg`；最终 DOM 检查见 `step5-browser-checks.json`。

## 交付边界

真实模型尚未配置，网页将该选项标为待配置，未运行或宣称真实模型业务通过率。
`/health` 的 ready_for_demo 仍为 false，待完成真实模型验收。
固定文字判据与有限反例不能证明所有自然语言表达都正确；规则安全边界另由单元测试覆盖。
政策、订单、身份、物流和工单均为模拟。本阶段没有发布公网网站或接入真实退款。

产品判断说明：`docs/product-decisions.md`；两分钟演示：`docs/demo-script.md`；启动及复跑命令见 README。
