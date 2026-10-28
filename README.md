# 电商售后 Agent · 服饰退货 MVP

当前完成数据层、Agent 主流程、R1–R4、三栏网页及第五步业务评测面板，可本地交互演示。
15 条离线业务评测已实际运行；真实验收使用 LiteLLM + ERNIE-5.1，
以实际保存报告为准，离线成绩不代表真实模型通过。
政策均为虚构演示规则，不代表真实平台政策。

## 环境与运行

Windows PowerShell，Python 3.12（当前环境已验证，锁定依赖需 3.12+）。首次准备：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

在仓库根目录执行，不需要激活虚拟环境：

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m aftersales.validate_data
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests/test_data.py -k money
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
```

第一条检查并汇总数据；pytest 运行数据层、主流程与规则的完整测试，`-k money` 只测金额转换；
Ruff 检查代码风格与格式。所有命令均从仓库根目录运行。

LiteLLM Python SDK 已安装到项目 `.venv`，版本锁定为 `1.106.2`，依赖列在 `requirements.txt`。
固定版本依据 [LiteLLM 官方公告](https://docs.litellm.ai/blog/security-incident-oct-21-2026)。
真实验收已接入 LiteLLM；HTTP 适配器作为显式备选保留，失败不会自动切换模型。

## 启动网页与 API

```powershell
$env:AGENT_MODE = 'offline'
.\.venv\Scripts\python.exe -m uvicorn aftersales.main:app --app-dir src --host 127.0.0.1 --port 8000
```

打开 [本地网页](http://127.0.0.1:8000/) 交互演示，接口文档见 `/docs`。
`/health` 返回 stage=5、rules_ready=true、web_ready=true、evaluation_ready=true；
真实模型尚未验收，因此 ready_for_demo=false。
离线模板模式无需模型密钥，使用真实检索，
服务端将已核对政策与订单事实转换为客服表达，不冒充自由生成模型。

### 网页的演示方式

宽屏显示三栏：对话、实际决策轨迹、当前消息的订单与政策。建议在 1280px 及以上窗口投屏；
800px 及以下按纵向排列。无需 Node、前端安装或构建命令，页面由同一个 FastAPI 服务托管。

默认买家 B，依次点击“政策问答”“信息追问”“订单退款”“投诉转人工”，
即可演示 P01、缺订单号、1280 元触发 R1、新投诉触发 R3。
轨迹使用实际响应中的事件；固定规则引用标明来源，不伪造检索命中或分数。
每条消息的“查看本轮轨迹”切换对应依据。右侧不沿用其他消息的订单。

切换买家 A 可查询 ORD-1001 等普通订单；输入“退货能不能上门取件？”触发低分追问，
点击“转人工核实”才创建工单。历史入口不可再次提交，后端同时校验身份、会话和来源 trace。
重置对话或切换身份清空三栏，新建会话；旧请求的迟到结果会被丢弃。

Enter 发送，Shift+Enter 换行；发送期间禁用重复提交。断线时显示未收到结果，不生成假的轨迹，
可在服务恢复后点击重新连接。服务重启清空内存会话和工单，需要重置对话。
最后点击顶栏“跑评测”，会执行全部 15 条用例并展开结果。可查看 E08 的规则、工单查验和实际回复，
再展开 F-MONEY-001 的真实失败与修复前后。底部摘要可单独展开，读取该模式最近的保存报告。
第四步原始浏览器检查见 [web.md](reports/web.md)，第五步记录见 [evaluations.md](reports/evaluations.md)。

### 业务评测与报告

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m evals.run --mode offline
# 配置服务端模型环境变量后才运行，失败不会切换为离线：
.\.venv\Scripts\python.exe -m evals.run --mode live
```

网页与 CLI 共用 `src/evals/` 的 15 条用例和判定器，通过隔离 app 的真实 `/api/chat`、订单工具和
`/api/handoffs/{id}` 接口执行。每条用例创建独立会话，评测另有自己的工单存储，不影响演示。
通过判据同时检查动作、引用、关键文字、真实工具事件与工单查验，不只匹配关键词。
固定用例和文字判据仍不能证明任意口语问题均正确，规则边界另由 pytest 覆盖。

每次报告写入 `reports/evaluations/<run_id>.json` 和同名 `.md`；重启后可读历史报告，
服务端会标记报告与当前代码、政策及配置指纹是否一致。保留每次记录，不覆盖首次成绩。
四类失败为“检索错误 / 该追问没追问 / 该转人工没转 / 编造答案”；执行错误单列，
所有未通过及未执行项均不会计入通过数。报告含代码/政策/数据配置指纹、模式、模型名和完整实际响应，
不记录模型密钥。离线与真实模型报告按模式分别读取。运行中断记录 failed，不能当成完成验收。

接口均需要本地演示身份头：`POST /api/evaluations` 接收 `{ "mode": "offline" }`，返回 202 与 run_id；
`GET /api/evaluations/{run_id}` 读取任务状态/进度；`GET /api/evaluations/latest?mode=offline` 读取最近报告。
同一模式并行点击复用运行中的任务，另一模式返回 409；浏览器每秒轮询，完成或查询失败后停止。
`GET /api/failure-cases` 返回已存在的历史开发失败证据，不虚构 E08 失败故事。
这套评测使用公开的模拟身份与订单夹具；不接真实客户数据，也不是生产访问控制方案。

产品说明见 [product-decisions.md](docs/product-decisions.md)，两分钟演示脚本见 [demo-script.md](docs/demo-script.md)。

在另一个 PowerShell 窗口发送请求：

```powershell
$headers = @{ 'X-Demo-Token' = 'local-buyer-a' }
$body = @{ message = '我想退货' } | ConvertTo-Json
$result = Invoke-RestMethod 'http://127.0.0.1:8000/api/chat' -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
$result
# 后续请求带上 $result.session_id，依次补充 ORD-1001 和尺码不合。
```

buyer-a / buyer-b 的公开本地模拟凭据分别为 `local-buyer-a` / `local-buyer-b`，
通过请求头传递，不能靠聊天文本改变身份。会话和订单基础归属检查已接入；
这不是生产认证系统。新请求省略 session_id 即新建会话。

订单客户端通过 HTTPX ASGI 传输调用独立模拟订单 API，保留请求、响应及错误语义，
不占用额外端口；轨迹明确记录 `in_process_asgi`，不假称调用了真实电商平台。
接口地址为 `/api/mock/orders/{order_id}`，金额序列化为十进制字符串；客户端校验后
转换为 Decimal，业务计算仍用整数分。方法参考 [HTTPX 官方传输文档](https://www.python-httpx.org/advanced/transports/)。

### 当前真实验收：ERNIE-5.1 + LiteLLM

在本地 `.env` 填写百度千帆 v2 API 密钥 `QIANFAN_API_KEY=`，运行：

```powershell
.\.venv\Scripts\python.exe scripts/start_ernie.py --check
.\.venv\Scripts\python.exe scripts/start_ernie.py --evaluate
# 停止旧服务后启动真实模型对话及评测：
.\.venv\Scripts\python.exe scripts/start_ernie.py
# 若需要保持聊天离线，仍可单独跑真实评测：
.\.venv\Scripts\python.exe scripts/start_ernie.py --web-mode offline
```

模型使用 `openai/ernie-5.1`（LiteLLM 路由前缀，服务端模型为 `ernie-5.1`），
地址为 `https://qianfan.baidubce.com/v2`，依据
[千帆 OpenAI 兼容接口](https://cloud.baidu.com/doc/qianfan/s/Hmh4suq26) 与
[LiteLLM 兼容端点](https://docs.litellm.ai/docs/providers/openai_compatible)。
启动器仅使用 `QIANFAN_API_KEY`，不混用智谱或 OpenAI 密钥；密钥只进入子进程环境。
历史 GLM 启动器 `scripts/start_glm_flash.py` 和原始报告保留，不自动回退模型。

模型仅选择政策证据；金额、低分、鉴权和工单规则继续由代码执行。
`verified_model_generations` 是成功校验的模型生成次数，其余用例由代码门控处理。
模型繁忙、超时、限流单列 execution_error，不计入通过数或四类业务错误。
智谱 1305 表示繁忙、1302 表示速率限制，详见[错误码文档](https://docs.bigmodel.cn/cn/api/api-code)。
应用限定网络发送预算：临时繁忙最多退避重试一次；余额或密钥错误不反复发送，也不自动换模型。

### 备选 HTTP 配置

配置 HTTP live 模式需在**启动前**设置以下环境变量，直接运行 uvicorn 不会自动读取 `.env`：

```powershell
$env:AGENT_MODE = 'live'
$env:MODEL_TRANSPORT = 'http'
$env:MODEL_BASE_URL = 'https://api.openai.com/v1'
$env:MODEL_API_KEY = '你的密钥'
$env:MODEL_NAME = 'gpt-6.1-sol'
```

适配器请求 `/chat/completions`，要求返回 policy_ids 和 evidence_quotes；
只接受命中政策的原文引用，再由服务端输出客服表达和资格模板。
缺配置时启动失败；调用失败或引用校验失败时澄清，不偷偷降级到离线模式。
HTTP 模式有协议替身回归；当前真实验收采用上面的 ERNIE LiteLLM 路径。
本步意图与槽位提取使用可观察规则，复杂表达保持未知；尚未实现模型语义提取。

### GPT-6.1 Sol 本地接入

已按官方 [GPT-6.1 Sol 模型页](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
及 [GPT-6 迁移指南](https://developers.openai.com/api/docs/guides/latest-model) 适配 `gpt-6.1-sol`：
使用 Chat Completions 做证据选择（不调用模型工具），低推理强度、严格 JSON Schema，移除 temperature。
订单查询、金额/低置信度门控、资格判断继续由代码执行。

在本地 `.env` 的 `MODEL_API_KEY=` 后填写 OpenAI API Key，然后执行：

```powershell
# 只检查配置是否存在，不访问网络，也不打印密钥：
.\.venv\Scripts\python.exe scripts/start_gpt_sol.py --check
# 独立执行 15 条真实模型业务评测：
.\.venv\Scripts\python.exe scripts/start_gpt_sol.py --evaluate
# 停止旧服务后启动真实模型网页：
.\.venv\Scripts\python.exe scripts/start_gpt_sol.py
```

此入口只把密钥读入子进程环境，不执行 `.env` 内容；固定使用 OpenAI 官方 API 地址和指定模型。
也支持启动进程已有的 `MODEL_API_KEY` 或 `OPENAI_API_KEY`，环境变量优先。
`.env` 已被 `.gitignore` 排除，不能把密钥提交或发进聊天。直接启动 uvicorn 仍不会自动加载 `.env`。
真实账户是否有模型访问权限，需成功请求后才能确认；缺密钥时保持离线演示，不伪造 live 结果。

无端口开发自检及独立检索探测：

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m aftersales.smoke_agent --output reports/local-smoke.json
.\.venv\Scripts\python.exe -m aftersales.probe_retrieval --output reports/local-retrieval.json
.\.venv\Scripts\python.exe -m aftersales.smoke_rules --output reports/local-rules.json
```

`smoke_agent` 自检问答、追问、查询和在途流程；`smoke_rules` 演练 R1–R4 并查验真实模拟工单，
均输出实际 API JSON 响应，不是 E01–E15 的正式评测器。若所在环境阻止 SciPy DLL 或临时目录访问，
应在获准的正常终端运行，不将环境错误计作业务通过。

## 数据与接口约定

- `data/policies.json`：P01–P12，一条对象一个检索 chunk，保留稳定来源 ID。
- `data/orders.json`：5 个模拟订单，保留原字段；金额经 Decimal 加载，以整数分供业务使用。
- `data/ownership.json`：buyer-a 拥有 1001/1002/1003/1005，buyer-b 拥有 1004。
- `data/settings.json`：固定上海时区时钟、500 元阈值、0.6 检索门槛等。
- `src/aftersales/`：不可变数据模型、完整数据集校验、固定时钟及日期窗口工具。
- `tests/`：正常数据及非法金额、日期、状态、归属、JSON、日历边界测试。
- `src/aftersales/main.py`：FastAPI 入口；`agent.py`：主流程；`retrieval.py`：真实检索。
- `tests/test_agent.py`：API、多轮追问、来源、失败路径与模型适配测试。
- `src/aftersales/rules.py`：金额、置信度与投诉门控；`handoffs.py`：内存模拟工单。
- `tests/test_rules.py`：阈值、权限、幂等、规则优先级与真实缺陷的回归测试。
- `web/`：无构建步骤的 HTML/CSS/JavaScript 三栏页面；`tests/test_web.py`：页面托管与数据边界测试。
- `GET /api/demo`：提供当前身份的演示订单选项、模式、日期与门槛，不能查询其他身份数据。

默认演示时间为 `2026-10-27T12:00:00+08:00`，与评测日期一致。
签收日为第 0 天，七天/十五天窗口截至相应日期的最后一微秒；并非 168 小时。
`reason_eligible` 仅为场景标签，不等于用户已提供原因；`note` 不参与业务判断。
凭证上传仅表示 `uploaded_unverified`，不能视为质量审核通过。
在途商品状态为 null，不默认完好。

加载入口为 `aftersales.data.load_dataset()`，返回政策、订单映射、归属、配置和时钟。
加载时拒绝重复编号、缺失记录、非法字段、未来签收和不完整归属。
按归属表限制查询及会话访问，未授权与不存在订单返回相同的 404。

## 第三步：硬规则与模拟工单

| 规则 | 实际行为 |
| --- | --- |
| R1 | 退款上下文取整单实付与明确请求金额的较大值，严格超过 50000 分即创建模拟工单；等于阈值不因金额转人工。 |
| R2 | top1 相似度低于 0.6 或分数无效时只追问，不调用生成器，不输出政策细节。 |
| R3 | 包含投诉/曝光/消协/律师或明确请求人工时直接建单，优先于缺参数和检索。 |
| R4 | 无匹配、超出自动判断范围或生成证据无效时说明无法确认，提供人工入口；点击后才建单。 |

R1/R3 强制转人工不依赖检索或模型。R1 使用 P12 固定政策引用，轨迹标明
“检索未执行；规则直接引用”，不会伪造检索分数。普通查询高额订单和解释 P12 不自动建单。
质量问题在 15 天范围内仍需核验凭证；上传不代表通过。超过七天或吊牌损坏不能直接否定质量争议。
缺失、非法或模糊金额先追问，金额仅在当前订单事项中保留；切单清理金额和原因。

人工入口 API：

- `POST /api/handoffs`：传当前 `session_id`、最近一轮 `trace_id`，返回 `ticket`、`reused` 和实际工单事件。
- `GET /api/handoffs/{handoff_id}?session_id=...`：仅允许同一身份和同一会话查看。
- 两个接口都需要 `X-Demo-Token`；其他身份或会话返回 404，过期/伪造的入口返回 409。
- 同一事项重复提交复用工单；退款事项与新投诉分别建单。工单号如 `TK-20261027-0001`。

低分问题的人工入口调用示例（`$result` 为聊天返回的最新响应）：

```powershell
$ticketBody = @{ session_id = $result.session_id; trace_id = $result.trace_id } | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8000/api/handoffs' -Method Post -Headers $headers -ContentType 'application/json' -Body $ticketBody
```

仅在 `handoff_available=true` 时提供手动入口；R1/R3 的 `handoff_id` 直接对应已创建记录。
所有会话、工单在内存中，服务重启清空；不代表真实客服、退货申请或退款已经执行。
本地公开模拟身份不是生产鉴权。自然语言提取仍有局限，超出明确支持的表述不保证正确分类。
第三步验证与真实失败修复见 [rules.md](reports/rules.md)。

一条政策仍是一个逻辑 chunk。标题、正文、别名和完整文本分别向量化，以该政策各字段的
真实余弦最大值排名，再按 ID 合并 Top 3；轨迹记录匹配字段与实际检索查询。
订单判断会使用规则确定的政策主题作为查询，纯政策问题使用用户原始问句。
0.6 不是正确概率；部分口语问法仍会安全拒答，详情见第二步报告。

后续实施顺序与验收标准见 [PROJECT_PLAN.md](PROJECT_PLAN.md)。

### 查看评测历史与修复对比

展开网页底部“评测面板”，选择“真实模型”，在“评测历史”下拉框选择一轮记录。
列表保留当前模式的所有历史模型，显示时间（上海时区）、模型、成绩和未通过用例；选择不会调用模型。
展开“ERNIE · E02 超时 → 调整预算后复测通过”可对照 14/15 与 15/15 的真实记录，
点击“查看该轮全部用例”后展开 E02，查看失败判据、执行错误及原始工具事件。
“读取最近结果”返回当前配置模型的最近报告；历史版本会显示提示，原报告不被修改。
`GET /api/evaluations/history?mode=live` 返回历史摘要和有真实来源的修复对比，需演示身份鉴权。

### 云端部署

现有 Python 后端可通过 Docker 部署；Render 配置与服务器步骤见 [部署说明](docs/deployment.md)。
云端入口需要独立访问密码和平台端千帆密钥；不能将本地 .env 上传到仓库。
