# ERNIE-5.1 接入与真实验收

- 调用链：LiteLLM 1.106.2 → 千帆 OpenAI 兼容接口 → ernie-5.1。
- 启动：`.\.venv\Scripts\python.exe scripts/start_ernie.py`，网页聊天与真实评测均使用新模型。
- 密钥：仅从本地 QIANFAN_API_KEY 读取；不混用其他供应商密钥、不自动降级模型。
- 模型负责政策证据提取；最终业务判断、金额、低置信度、鉴权和工单均由代码控制。

## 真实失败与修复

首轮报告：`evaluations/804a9db72ebf49f8b4a4165f901a02b5.json`，14/15。
E02 在原单次15秒预算内超时，两次发送后安全追问，未输出退款结论；归为执行错误。
调整 ERNIE 单次请求超时为30秒（外层35秒），最多两次发送，保留 GLM 原配置。
这是超时预算调整后的单轮成功记录，不能据此保证长期稳定性。

复测报告：`evaluations/e0cc6c1d9f5e4458aa1256a4a4d7eb3e.json`，15/15，执行错误0。
4次真实模型证据生成经校验通过；其余11条主要验证代码门控，不能称为15次模型生成。
原 GLM 报告与首次 ERNIE 失败报告均保留；网页最近真实结果按当前模型与传输方式筛选。

## 验证

- 全量 pytest：228 passed；超时调整后供应商相关回归：19 passed。
- Ruff 检查和格式校验通过。
- 离线业务评测：15/15，报告 `evaluations/588c70059e19476881fa9b7de9a1d4a1.json`。
- 浏览器已确认“真实模型模式”和 ERNIE 15/15；截图：`ernie-live-desktop.jpg`。
- 未修改前端布局或交互；保留本地模拟订单与工单，不执行真实退款。

## 官方接口依据

- https://cloud.baidu.com/doc/qianfan/s/Hmh4suq26
- https://cloud.baidu.com/doc/qianfan/s/rmh4stp0j
- https://docs.litellm.ai/docs/providers/openai_compatible
