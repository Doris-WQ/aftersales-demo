"""第三步 API 演练；不冒充 E01–E15 正式评测。"""

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from aftersales.main import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    turns = []
    tickets = []
    with TestClient(create_app()) as client:
        headers = {"X-Demo-Token": "local-buyer-b"}
        session_id = None
        for message in (
            "七天无理由从哪天算？",
            "我想退货",
            "ORD-1004 我要退款",
            "你们再这样我投诉",
        ):
            response = client.post(
                "/api/chat", headers=headers, json={"session_id": session_id, "message": message}
            )
            response.raise_for_status()
            result = response.json()
            session_id = result["session_id"]
            turns.append({"buyer": "buyer-b", "input": message, "output": result})
            if result["handoff_id"]:
                ticket = client.get(
                    f"/api/handoffs/{result['handoff_id']}",
                    headers=headers,
                    params={"session_id": session_id},
                )
                ticket.raise_for_status()
                tickets.append(ticket.json())
        headers = {"X-Demo-Token": "local-buyer-a"}
        for message in ("退货能不能上门取件？", "ORD-1005 有质量问题，退我1000"):
            response = client.post("/api/chat", headers=headers, json={"message": message})
            response.raise_for_status()
            result = response.json()
            turns.append({"buyer": "buyer-a", "input": message, "output": result})
            if result["handoff_available"]:
                ticket = client.post(
                    "/api/handoffs",
                    headers=headers,
                    json={"session_id": result["session_id"], "trace_id": result["trace_id"]},
                )
                ticket.raise_for_status()
                tickets.append(ticket.json())
            elif result["handoff_id"]:
                ticket = client.get(
                    f"/api/handoffs/{result['handoff_id']}",
                    headers=headers,
                    params={"session_id": result["session_id"]},
                )
                ticket.raise_for_status()
                tickets.append(ticket.json())
        output = {
            "health": client.get("/health").json(),
            "turns": turns,
            "tickets": tickets,
            "formal_15_case_evaluation_run": False,
        }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    for turn in turns:
        response = turn["output"]
        print(
            json.dumps(
                {
                    "input": turn["input"],
                    "action": response["action"],
                    "rules": response["triggered_rules"],
                    "handoff_id": response["handoff_id"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
