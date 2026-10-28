# Repository Guidelines

## 项目结构与模块组织

本项目是单渠道服饰退货 Agent MVP，已实现三栏网页及离线业务评测，真实模型验收待完成。`src/aftersales/` 存放模型、检索、编排、规则和工单，`src/evals/` 存放业务用例与共享评测器，`web/` 存放原生 HTML/CSS/JavaScript，`data/` 存放模拟数据，`tests/` 存放测试，`reports/` 保存验证记录。实施顺序和边界见 `PROJECT_PLAN.md`。

## 构建、测试与开发命令

在仓库根目录创建 Python 3.12 虚拟环境并执行 `python -m pip install -r requirements.txt`。设置 `PYTHONPATH=src` 后，运行 `python -m aftersales.validate_data` 校验数据；`python -m pytest` 运行测试；`python -m ruff check src tests` 和 `python -m ruff format --check src tests` 检查代码。`python -m uvicorn aftersales.main:app --app-dir src --host 127.0.0.1` 启动网页与 API。无需前端构建，完整示例见 `README.md`。

## 编码风格与命名规范

Python 使用四空格缩进，函数与模块采用 `snake_case`，类采用 `PascalCase`，通过 Ruff 统一格式。政策 ID 固定为 P01–P12，订单 ID 固定为 ORD-1001–ORD-1005。金额从 JSON 以 Decimal 加载，再转换为整数分；禁止浮点金额参与判断。未知状态保留 null，备注与场景标签不得替代用户输入。

## 测试指南

使用 pytest，测试文件为 `test_*.py`，名称描述场景和预期。新增规则应覆盖边界与失败路径，缺陷修复应添加回归用例。运行 `python -m pytest tests/test_data.py -k money` 可单测金额转换。尚未设置覆盖率门槛；单元测试不得冒充 E01–E15 业务成绩。变更后运行相关测试及 `python -m evals.run --mode offline`，保留每次报告；涉及模型适配时另跑 live，未配置时明确待验收。

R1/R3 必须先于生成器执行；R2 低分时禁止业务答案。引用来源应区分检索和规则。工单必须真实创建在内存服务中并校验身份、会话和事项，禁止伪造工单或全通过评测结果。

网页用文本节点呈现用户和政策内容。身份切换、重置应清空三栏并忽略过期请求结果；轨迹只能读取服务端事件。页面变更需在浏览器验证桌面、窄屏、断线与历史消息切换，不能用 API 测试替代界面检查。

## 提交与拉取请求规范

当前目录尚未初始化 Git，无提交历史可供归纳。后续提交说明建议使用简短的动作描述，例如“添加配置加载逻辑”或“修复空输入处理”。每次提交聚焦一个目的。拉取请求应说明变更目的、主要修改和验证结果，适用时关联问题；涉及界面变化时附截图，并明确新增依赖或配置要求。

## 安全与配置

禁止提交密钥、访问令牌、凭据和本地私有配置。需要配置示例时，使用 `.env.example` 等示例文件并填写占位值；引入相关文件时配置 `.gitignore`，排除真实配置、构建产物和本地缓存。日志及测试数据同样不得包含敏感信息。
