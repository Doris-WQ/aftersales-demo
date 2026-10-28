"""无需启动端口的开发自检；真实调用 ASGI API 并保存响应。"""

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from aftersales.main import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    scenarios = (
        ("policy", ("七天无理由从哪天算？",)),
        ("refund_time", ("退款多久到账？",)),
        ("slots", ("我想退货", "ORD-1001", "尺码不合")),
        ("in_transit", ("ORD-1003 还没收到，能退吗？",)),
        ("no_policy", ("退货能不能上门取件？",)),
    )
    records = []
    with TestClient(create_app()) as client:
        for scenario, messages in scenarios:
            session_id = None
            for message in messages:
                response = client.post(
                    "/api/chat",
                    headers={"X-Demo-Token": "local-buyer-a"},
                    json={"session_id": session_id, "message": message},
                )
                response.raise_for_status()
                result = response.json()
                session_id = result["session_id"]
                records.append({"scenario": scenario, "input": message, "output": result})
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    for record in records:
        result = record["output"]
        print(
            json.dumps(
                {
                    "scenario": record["scenario"],
                    "action": result["action"],
                    "reason": result["reason_code"],
                    "score": result["retrieval_score"],
                    "policy_ids": result["policy_ids"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
