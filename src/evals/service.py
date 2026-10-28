"""单进程评测任务；原子报告持久化，重启后只恢复历史完成报告。"""

import asyncio
import json
import os
from pathlib import Path

from aftersales.generation import ModelConfig
from evals.run import REPORTS, ROOT, execute, fingerprint, new_report, now, persist, summarize


class EvaluationService:
    def __init__(self, dataset, directory: Path = REPORTS):
        self.dataset = dataset
        self.directory = directory
        self.runs = {}
        self.task = None
        self.active_id = None
        self.lock = asyncio.Lock()
        self.current_fingerprints = fingerprint(dataset)

    def view(self, report):
        if report is None:
            return None
        return {
            **report,
            "matches_current_version": report["fingerprints"] == self.current_fingerprints,
        }

    async def start(self, mode):
        if mode == "live":
            ModelConfig.from_env()  # missing configuration is explicit, never falls back to offline
        async with self.lock:
            if self.task and not self.task.done():
                if self.runs[self.active_id]["mode"] != mode:
                    raise RuntimeError("另一种模式的评测正在执行")
                return self.runs[self.active_id], True
            report = new_report(mode, self.dataset)
            self.runs[report["run_id"]] = report
            self.active_id = report["run_id"]
            self.task = asyncio.create_task(self._run(report))
            return report, False

    async def _run(self, report):
        try:
            await execute(report, self.dataset, self.directory)
        except asyncio.CancelledError:
            report["status"] = "failed"
            report["error"] = "服务停止，评测未完成；未执行用例不计通过。"
            raise
        except Exception:
            report["status"] = "failed"
            report["error"] = "评测执行或报告保存失败，请检查本地服务。"
        finally:
            if report["status"] != "completed":
                report["finished_at"] = now()
                summarize(report)
                persist(report, self.directory)

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def get(self, run_id):
        if run_id in self.runs:
            return self.runs[run_id]
        if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
            return None
        path = self.directory / f"{run_id}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def latest(self, mode):
        candidates = [r for r in self.runs.values() if r["mode"] == mode]
        if self.directory.exists():
            for path in self.directory.glob("*.json"):
                try:
                    report = json.loads(path.read_text(encoding="utf-8"))
                    if report["mode"] == mode and report["status"] in ("completed", "failed"):
                        candidates.append(report)
                except (OSError, ValueError, KeyError):
                    continue
        if mode == "live" and os.getenv("MODEL_NAME"):
            candidates = [
                r
                for r in candidates
                if r.get("model") == os.environ["MODEL_NAME"]
                and r.get("transport") == os.getenv("MODEL_TRANSPORT", "http")
            ]
        return max(candidates, key=lambda r: r["started_at"], default=None)

    def history(self, mode):
        """List saved runs across models without returning complete conversation bodies."""
        identifiers = set(self.runs)
        if self.directory.exists():
            identifiers.update(p.stem for p in self.directory.glob("*.json"))
        reports = []
        for run_id in identifiers:
            report = self.get(run_id)
            required = ("run_id", "mode", "started_at", "status", "passed", "total", "fingerprints")
            if not isinstance(report, dict) or not all(k in report for k in required):
                continue
            if report["mode"] != mode or report["run_id"] != run_id:
                continue
            summary = {k: report[k] for k in required if k != "fingerprints"}
            summary.update(
                model=report.get("model"),
                execution_errors=report.get("execution_errors", 0),
                failed_cases=[r["id"] for r in report.get("results", []) if not r["passed"]],
                matches_current_version=report["fingerprints"] == self.current_fingerprints,
            )
            reports.append(summary)
        return sorted(reports, key=lambda r: (r["started_at"], r["run_id"]), reverse=True)

    def timeout_comparison(self):
        """Only show the documented ERNIE comparison when both source reports exist."""
        before = self.get("804a9db72ebf49f8b4a4165f901a02b5")
        after = self.get("e0cc6c1d9f5e4458aa1256a4a4d7eb3e")
        if not before or not after:
            return None
        sides = []
        for report in (before, after):
            result = next((r for r in report.get("results", []) if r["id"] == "E02"), None)
            if result is None or report.get("model") != "openai/ernie-5.1":
                return None
            sides.append(
                {
                    "run_id": report["run_id"],
                    "passed": report["passed"],
                    "total": report["total"],
                    "case": result,
                }
            )
        if sides[0]["case"]["passed"] or not sides[1]["case"]["passed"]:
            return None
        return {"before": sides[0], "after": sides[1]}


def failure_cases():
    """Only recorded evidence files; never invent an E08 failure story."""
    output = []
    for filename in ("failure-amount.json", "failure-retrieval.json"):
        path = ROOT / "reports" / filename
        if path.exists():
            evidence = json.loads(path.read_text(encoding="utf-8"))
            output.append({"source_file": f"reports/{filename}", "record": evidence})
    return output
