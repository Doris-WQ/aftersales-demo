# 第一步：数据层验证记录

本记录仅涉及数据层；未执行 E01–E15 业务评测，尚未实现 Agent 和网页。

## 已创建数据

- 12 条独立政策 chunk，ID 为 P01–P12，版本 demo-v1。
- 5 个模拟订单，保留用户原始字段，补充商品与凭证结构化状态。
- 2 个模拟买家归属；默认 buyer-b 可访问 ORD-1004。
- 固定演示时钟 2026-10-27T12:00:00+08:00。

## 实际验证结果

- 数据加载自检：status=ok，policies=12，orders=5，buyers=2。
- `python -m pytest -q --tb=short`：60 passed，0.38 秒。
- `python -m ruff check src tests`：All checks passed。
- `python -m ruff format --check src tests`：6 files already formatted。
- 当前项目虚拟环境中的依赖版本已锁定在 requirements.txt。

金额 499.99/500.00/500.01 的测试仅证明精确转换为整数分；尚不证明 R1 已生效。
七天/十五天窗口按上海日历计算，包含截止日最后一微秒并拒绝未来签收日期。
归属测试仅证明数据映射有效，不代表已实现 API 鉴权。

首次沙箱运行：15 passed、45 个临时目录创建错误，未取得有效完整结果。
随后在获准的沙箱外环境重跑，60 项全部通过；环境错误不冒充模型失败样本。

## 后续阶段

本步止于加载与校验。待用户确认后进入第二步 Agent 主流程。
