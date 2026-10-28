"""命令行数据自检，不输出订单隐私或执行任何业务动作。"""

import json

from aftersales.data import load_dataset


def main():
    dataset = load_dataset()
    print(
        json.dumps(
            {
                "status": "ok",
                "policies": len(dataset.policies),
                "orders": len(dataset.orders),
                "buyers": len(dataset.ownership),
                "policy_version": dataset.settings.policy_version,
                "demo_now": dataset.clock.now().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
