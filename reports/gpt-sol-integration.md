# GPT-6.1 Sol 接入准备

## 已完成

- 保留指定模型 `gpt-6.1-sol`，官方地址 `https://api.openai.com/v1`。
- 现有文本证据选择使用 Chat Completions，不向模型开放工具调用；金额、低分、鉴权、工单等代码门控不变。
- 该模型使用 reasoning_effort=low 和严格 JSON Schema，移除不兼容的 temperature 参数。
- `scripts/start_gpt_sol.py` 只从本地 `.env` 或进程环境读取密钥；不执行文件内容、不打印密钥，
  分别支持 --check、--evaluate 和启动网页。未改变本机 PowerShell 执行策略。
- 已准备被 Git 忽略的 `.env` 密钥填写位置；目前为空，未进行真实 API 请求。

## 实际验证

- `pytest`：209 passed，包含模型参数与证据契约、密钥文本不执行及不输出、缺密钥中止测试。
  记录见 `gpt-sol-tests.xml`；HTTP 协议测试使用替身，不代表真实账户访问权限。
- Ruff 检查与格式通过。
- 最新离线业务报告 `evaluations/6100645cac954600803e65537eb4e4ef.json`：15/15。
- 预检确认缺密钥时退出码为 2；没有伪造真实模型报告。

## 待完成

用户在本地 `.env` 填写 MODEL_API_KEY 后，运行 `scripts/start_gpt_sol.py --evaluate`，
检查 API 认证、模型权限、真实生成结果、完整 15 条用例及硬边界。
成功验证前，网页继续使用离线演示，不宣称已完成真实模型验收。

## 官方依据

- [模型 ID 与能力](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [推理参数及迁移兼容性](https://developers.openai.com/api/docs/guides/latest-model)
