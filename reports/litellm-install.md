# LiteLLM 安装验证

- 安装环境：`Q:\Project01\.venv`，Python 3.12。
- 安装命令：`python -m pip install litellm==1.106.2 -c requirements.txt --index-url https://pypi.org/simple`。
- 按 [LiteLLM 官方事件公告](https://docs.litellm.ai/blog/security-incident-oct-21-2026) 固定 1.106.2，未安装受影响的 1.107.0。
- 安装结果：成功。安装包元数据和下载摘要见 `litellm-install.json`。
- `pip check`：No broken requirements found。
- 导入验证：版本为 1.106.2，`litellm.acompletion` 可调用；使用包自带本地成本表，没有调用真实模型。
- 原有依赖版本保持不变，新增依赖已锁定到 `requirements.txt`。
- 完整回归：209 passed，记录见 `litellm-install-tests.xml`；仅一条已知 Starlette/httpx 弃用提示。
- 离线业务：15/15，报告 `evaluations/04df57414b7d439580addc51c3713210.json`。

本次仅安装 SDK；没有启动 LiteLLM Proxy、切换 Agent 适配器或进行付费模型请求。
