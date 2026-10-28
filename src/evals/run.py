"""共享异步评测器与命令行。每次运行独立 app、会话、订单客户端和工单存储。"""

import argparse
import asyncio
import hashlib
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from aftersales.data import Dataset, load_dataset
from evals.judge import CATEGORIES, judge

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "evaluations"


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="microseconds")


def cases():
    return json.loads(Path(__file__).with_name("cases.json").read_text(encoding="utf-8"))


def fingerprint(dataset: Dataset):
    source = hashlib.sha256()
    for path in sorted((ROOT / "src").rglob("*")):
        if path.suffix in (".py", ".json"):
            source.update(path.relative_to(ROOT).as_posix().encode())
            source.update(path.read_bytes())
    policy = json.dumps([p.model_dump(mode="json") for p in dataset.policies], sort_keys=True)
    configuration = json.dumps(
        {
            "settings": dataset.settings.model_dump(mode="json"),
            "orders": {k: v.model_dump(mode="json") for k, v in dataset.orders.items()},
            "ownership": dict(dataset.ownership),
        },
        sort_keys=True,
    )
    return {
        "code": source.hexdigest(),
        "policy": hashlib.sha256(policy.encode()).hexdigest(),
        "configuration": hashlib.sha256(configuration.encode()).hexdigest(),
    }


def new_report(mode: str, dataset: Dataset):
    return {
        "run_id": uuid4().hex,
        "status": "queued",
        "mode": mode,
        "model": "offline-evidence-template" if mode == "offline" else os.getenv("MODEL_NAME", ""),
        "transport": "offline" if mode == "offline" else os.getenv("MODEL_TRANSPORT", "http"),
        "verified_model_generations": 0,
        "started_at": now(),
        "finished_at": None,
        "demo_date": dataset.clock.today().isoformat(),
        "policy_version": dataset.settings.policy_version,
        "fingerprints": fingerprint(dataset),
        "total": len(cases()),
        "completed": 0,
        "passed": 0,
        "effective_executions": 0,
        "execution_errors": 0,
        "pass_rate": 0,
        "failure_counts": dict.fromkeys(CATEGORIES, 0),
        "category_results": {},
        "results": [],
        "scope": "固定15条模拟业务用例；不代表生产环境或真实退款验收",
    }


def summarize(report):
    results = report["results"]
    report["completed"] = len(results)
    report["passed"] = sum(r["passed"] for r in results)
    report["execution_errors"] = sum(r["execution_error"] is not None for r in results)
    report["verified_model_generations"] = (
        sum(
            e["step"] == "generation" and e["status"] == "ok"
            for r in results
            if r["actual"]
            for e in r["actual"]["trace_events"]
        )
        if report["mode"] == "live"
        else 0
    )
    report["effective_executions"] = len(results) - report["execution_errors"]
    report["pass_rate"] = round(report["passed"] / report["total"], 4)
    counts = Counter(c for r in results for c in r["failure_categories"])
    report["failure_counts"] = {c: counts[c] for c in CATEGORIES}
    report["category_results"] = {
        c: {
            "passed": sum(r["passed"] for r in results if r["category"] == c),
            "total": sum(case["category"] == c for case in cases()),
        }
        for c in ("正常问答", "信息不足", "高风险", "无答案")
    }


def persist(report, directory=REPORTS):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{report['run_id']}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    lines = [
        f"# 业务评测 · {report['mode']}",
        "",
        f"运行：{report['run_id']} · {report['started_at']} · {report['status']}",
        f"通过 {report['passed']}/{report['total']} · 执行错误 {report['execution_errors']}",
        f"代码指纹：{report['fingerprints']['code']}",
        "",
        "| 用例 | 结果 | 失败分类 | 实际行为摘要 | 修复动作 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in report["results"]:
        text = result["summary"].replace("\n", " ").replace("|", "／")
        lines.append(
            f"| {result['id']} | {'✅' if result['passed'] else '❌'} | "
            f"{' / '.join(result['failure_categories']) or result['execution_error'] or '—'} | "
            f"{text} | {result['fix_action']} |"
        )
    lines += [
        "",
        report["scope"],
        "",
        "本报告实际响应、工具事件、判据和工单查验保存在同名 JSON；离线与真实模型分别统计。",
    ]
    target.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


async def execute(report, dataset: Dataset, directory=REPORTS):
    from aftersales.main import create_app

    report["status"] = "running"
    # No shared app.state.agent: running evaluations must not affect demo conversations.
    app = create_app(dataset=dataset, evaluations_enabled=False, mode_override=report["mode"])
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://evaluation", trust_env=False
        ) as client,
    ):
        for case in cases():
            result = {
                "id": case["id"],
                "category": case["category"],
                "input": case["input"],
                "buyer": f"buyer-{case['buyer']}",
                "expected": case["expected"],
                "passed": False,
                "failure_categories": [],
                "checks": [],
                "actual": None,
                "verified_ticket": None,
                "execution_error": None,
                "summary": "",
                "fix_action": "—",
            }
            try:
                headers = {"X-Demo-Token": f"local-buyer-{case['buyer']}"}
                response = await client.post(
                    "/api/chat", headers=headers, json={"message": case["input"]}
                )
                response.raise_for_status()
                actual = response.json()
                result["actual"] = actual
                ticket = None
                if actual["handoff_id"]:
                    verification = await client.get(
                        f"/api/handoffs/{actual['handoff_id']}",
                        headers=headers,
                        params={"session_id": actual["session_id"]},
                    )
                    verification.raise_for_status()
                    ticket = verification.json()
                checks = judge(case, actual, ticket)
                result["checks"] = checks
                result["verified_ticket"] = ticket
                result["failure_categories"] = sorted(
                    {c["failure_category"] for c in checks if not c["passed"]}
                )
                result["passed"] = all(c["passed"] for c in checks)
                result["summary"] = actual["message"]
                if any(e["status"] == "error" for e in actual["trace_events"]):
                    result["execution_error"] = "agent_execution_error"
                    result["passed"] = False
                    # A safe abstention due to provider failure is an execution
                    # error, not hallucination or failed policy retrieval.
                    result["failure_categories"] = []
            except (httpx.HTTPError, KeyError, ValueError, TypeError):
                # Do not persist provider responses, credentials or exception text.
                result["execution_error"] = "request_or_contract_error"
                result["summary"] = "执行或响应契约异常；本条未通过。"
            if not result["passed"]:
                result["fix_action"] = "待处理；检查失败判据与实际轨迹"
            report["results"].append(result)
            summarize(report)
            await asyncio.sleep(0)  # allow progress reads without artificial delays
    report["status"] = "completed"
    report["finished_at"] = now()
    persist(report, directory)
    return report


async def cli(mode):
    dataset = load_dataset()
    report = new_report(mode, dataset)
    try:
        await execute(report, dataset)
    except Exception:
        report["status"] = "failed"
        report["error"] = "评测未能完成，请检查模式配置和本地依赖；未执行用例不计通过。"
        report["finished_at"] = now()
        summarize(report)
        persist(report)
    print(
        f"{mode}: {report['passed']}/{report['total']} · {REPORTS / (report['run_id'] + '.json')}"
    )
    return 0 if report["status"] == "completed" and report["passed"] == report["total"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    arguments = parser.parse_args()
    raise SystemExit(asyncio.run(cli(arguments.mode)))
