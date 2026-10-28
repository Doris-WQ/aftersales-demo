# GLM-4.7-Flash 真实验收

## 接入与边界

使用 LiteLLM 1.106.2，模型 `zai/glm-4.7-flash`，国内站地址
`https://open.bigmodel.cn/api/paas/v4`。密钥从本地 `.env` 的 ZHIPUAI_API_KEY 读取，不进入报告。
国际站通过 --region global 使用独立 ZAI_API_KEY。启动与复跑见 README。

R1/R2/R3、鉴权和工单仍由代码执行；只有检索通过且适合回答的用例调用模型选择证据。
模型不执行退款，业务回复继续由服务端呈现。不会把 15 条全部宣称为模型生成测试。

## 实际结果

- 完整 pytest：**224 passed**，`glm-litellm-tests.xml`；Ruff 检查及 34 个 Python 文件格式通过。
- 最终离线业务：**15/15**，`evaluations/8acc12b499744435b8c1930b79c5a9b6.json`。
- 最终真实业务：**11/15，执行错误 4，成功校验模型生成 0 次**，
  `evaluations/b87e1450271541a996e0425a2a375493.json`。
- 此前真实一轮 **12/15，成功校验模型生成 1 次（E03）**，
  `evaluations/a1144f0faf844622b41e4dc986d2c704.json`。这是较早版本记录，不替代最终成绩。
- 所有尝试报告均保留，包括首轮 `1481fb6ba2f24b179931a7120ca677b4`。没有把失败改成通过。

最终失败：E01 返回智谱 1305（繁忙）；E03/E04 返回 1302（速率限制）；
E02 为供应商调用异常，未获得可确认的业务错误码，不推断为余额或密钥问题。
模型故障单列 execution_error，不冒充四类业务错误，也不计入通过数。
高风险、追问和无答案的代码门控全部通过。当前**尚未达到真实模型至少 14/15 的验收标准**。

## 一条实际格式失败与修复

E01 独立重放时捕获到 GLM 正确复制 P01，但外层返回
`{"answer":[{"policy_ids":["P01"],"evidence_quotes":["…"]}]}`，严格契约拒绝它。
修复仅展开“外层唯一键 answer、值为单元素列表”的已观察结构；内部仍严格验证两个数组，
禁止额外字段，并由 Agent 校验全部必要政策 ID 与原文引用。不是从任意文本提取答案。
回归同时验证：合法包装可展开，带退款批准等额外字段仍拒绝。
证据见 `failure-glm-format.json`；修复后的最终真实请求仍受服务繁忙影响，未宣称该轮已经通过。

## 可靠性与页面

SDK 默认客户端会追加底层重试；应用使用明确的网络发送预算，每次尝试只允许一次发送。
临时 1302/1305 仅退避一次，1113 等配额错误不重试。实际 SDK 路由的 HTTP 替身验证了发送次数，
不只替换 acompletion 函数。所有错误只保留固定类别和数字码，不保存供应商异常原文或推理内容。

网页已开放“真实模型”选项，展示指定模型、LiteLLM、成功证据生成次数、执行错误和失败明细。
聊天暂保留离线演示，独立真实评测不会污染会话。/health 仍保留真实模型待验收状态。
待供应商恢复后，使用网页“真实模型”重新运行，或执行 `scripts/start_glm_flash.py --evaluate`。

## 官方依据

- [LiteLLM Z.ai 路由](https://docs.litellm.ai/docs/providers/zai)
- [智谱 GLM-4.7-Flash](https://docs.bigmodel.cn/cn/guide/models/free/glm-4.7-flash)
- [智谱业务错误码](https://docs.bigmodel.cn/cn/api/api-code)
