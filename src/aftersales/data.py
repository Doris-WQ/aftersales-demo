"""加载并校验完整数据集；订单授权由后续 API 使用此处归属表实现。"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from pydantic import TypeAdapter

from aftersales.clock import DemoClock
from aftersales.models import Order, OrderId, Policy, Settings, Text

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复 JSON 字段：{key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"非法 JSON 数值：{value}")


def read_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8-sig"),
        parse_float=Decimal,
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_keys,
    )


@dataclass(frozen=True)
class Dataset:
    policies: tuple[Policy, ...]
    orders: Mapping[str, Order]
    ownership: Mapping[str, tuple[str, ...]]
    settings: Settings
    clock: DemoClock


def load_dataset(directory: Path = DATA_DIR) -> Dataset:
    directory = Path(directory)
    settings = Settings.model_validate(read_json(directory / "settings.json"))
    clock = DemoClock(settings.demo_now)
    policies = TypeAdapter(tuple[Policy, ...]).validate_python(
        read_json(directory / "policies.json")
    )
    orders = TypeAdapter(tuple[Order, ...]).validate_python(read_json(directory / "orders.json"))
    ownership = TypeAdapter(dict[Text, tuple[OrderId, ...]]).validate_python(
        read_json(directory / "ownership.json")
    )
    policy_ids = [policy.id for policy in policies]
    if len(policy_ids) != len(set(policy_ids)):
        raise ValueError("政策编号重复")
    if set(policy_ids) != {f"P{i:02d}" for i in range(1, 13)}:
        raise ValueError("必须包含 P01–P12 共 12 条政策")
    if any(policy.version != settings.policy_version for policy in policies):
        raise ValueError("政策版本与配置不一致")
    order_ids = [order.order_id for order in orders]
    if len(order_ids) != len(set(order_ids)):
        raise ValueError("订单编号重复")
    if set(order_ids) != {f"ORD-{i}" for i in range(1001, 1006)}:
        raise ValueError("必须包含 ORD-1001–ORD-1005 共 5 个订单")
    if any(order.signed_date and order.signed_date > clock.today() for order in orders):
        raise ValueError("签收日期不能晚于演示日期")
    owned_ids = [order_id for ids in ownership.values() for order_id in ids]
    if len(owned_ids) != len(set(owned_ids)):
        raise ValueError("订单不能重复归属")
    if set(owned_ids) != set(order_ids):
        raise ValueError("归属必须覆盖全部订单，且不能引用不存在的订单")
    if settings.default_buyer not in ownership:
        raise ValueError("默认身份不存在")
    return Dataset(
        policies,
        MappingProxyType({order.order_id: order for order in orders}),
        MappingProxyType(ownership),
        settings,
        clock,
    )
