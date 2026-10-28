"""本地三栏演示、隔离业务评测和受控 API。"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aftersales.agent import Agent
from aftersales.contracts import (
    ChatRequest,
    ChatResponse,
    HandoffRequest,
    HandoffResult,
    HandoffTicket,
)
from aftersales.data import Dataset, load_dataset
from aftersales.generation import Generator, HttpGenerator, ModelConfig, OfflineGenerator
from aftersales.handoffs import HandoffUnavailable, TicketNotFound
from aftersales.litellm_generation import LiteLLMGenerator
from aftersales.orders import OrderClient, create_order_api, require_buyer
from aftersales.retrieval import PolicyRetriever
from aftersales.sessions import SessionNotFound


def create_app(
    dataset: Dataset | None = None,
    generator: Generator | None = None,
    order_transport: httpx.AsyncBaseTransport | None = None,
    retriever: PolicyRetriever | None = None,
    evaluations_enabled: bool = True,
    mode_override: str | None = None,
    evaluation_directory: Path | None = None,
) -> FastAPI:
    dataset = dataset or load_dataset()
    mock = create_order_api(dataset)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        mode = mode_override or os.getenv("AGENT_MODE", "offline")
        if mode not in ("offline", "live"):
            raise ValueError("AGENT_MODE 只能是 offline 或 live")
        async with (
            httpx.AsyncClient(
                transport=order_transport or httpx.ASGITransport(app=mock),
                base_url="http://mock",
                trust_env=False,
            ) as orders,
            httpx.AsyncClient(trust_env=False, follow_redirects=False) as model_client,
        ):
            if generator is not None:
                selected = generator
            elif mode == "offline":
                selected = OfflineGenerator()
            else:
                config = ModelConfig.from_env()
                selected = (
                    LiteLLMGenerator(config)
                    if config.transport == "litellm"
                    else HttpGenerator(model_client, config)
                )
            app.state.agent = Agent(dataset, OrderClient(orders), selected, retriever)
            if evaluations_enabled:
                from evals.run import REPORTS
                from evals.service import EvaluationService

                app.state.evaluations = EvaluationService(dataset, evaluation_directory or REPORTS)
            try:
                yield
            finally:
                if evaluations_enabled:
                    await app.state.evaluations.close()

    app = FastAPI(title="电商售后 Agent · 三栏演示工作台", lifespan=lifespan)
    app.mount("/api/mock", mock)
    web_dir = Path(__file__).resolve().parents[2] / "web"
    app.mount("/assets", StaticFiles(directory=web_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(web_dir / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/demo")
    async def demo(buyer: Annotated[str, Depends(require_buyer)]):
        return {
            "buyer": buyer,
            "channel": dataset.settings.channel,
            "mode": app.state.agent.generator.mode,
            "default_buyer": dataset.settings.default_buyer,
            "demo_date": dataset.clock.today().isoformat(),
            "policy_count": len(dataset.policies),
            "order_count": len(dataset.orders),
            "refund_limit_cents": dataset.settings.refund_limit_cents,
            "retrieval_threshold": float(dataset.settings.retrieval_threshold),
            "policy_version": dataset.settings.policy_version,
            "stage": 5,
            "evaluation_status": "available" if evaluations_enabled else "isolated_runner",
            "live_evaluation_available": all(
                os.getenv(name) for name in ("MODEL_BASE_URL", "MODEL_API_KEY", "MODEL_NAME")
            ),
            "orders": [
                {
                    "order_id": order_id,
                    "item": dataset.orders[order_id].item,
                    "amount": str(dataset.orders[order_id].amount),
                    "status": dataset.orders[order_id].status,
                }
                for order_id in dataset.ownership[buyer]
            ],
        }

    @app.get("/health")
    async def health():
        return {
            "status": "development",
            "stage": 5,
            "rules_ready": True,
            "web_ready": True,
            "evaluation_ready": evaluations_enabled,
            "ready_for_demo": False,
            "mode": app.state.agent.generator.mode,
            "policy_version": dataset.settings.policy_version,
            "demo_now": dataset.clock.now().isoformat(),
            "pending": ["真实模型验收"],
        }

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(
        request: ChatRequest,
        buyer: Annotated[str, Depends(require_buyer)],
        x_demo_token: Annotated[str, Header()],
    ):
        try:
            return await app.state.agent.chat(request, buyer, x_demo_token)
        except SessionNotFound:
            raise HTTPException(404, "会话不存在，请新建对话") from None

    @app.post("/api/handoffs", response_model=HandoffResult)
    async def handoff(request: HandoffRequest, buyer: Annotated[str, Depends(require_buyer)]):
        try:
            return await app.state.agent.request_handoff(request, buyer)
        except SessionNotFound:
            raise HTTPException(404, "会话不存在，请新建对话") from None
        except HandoffUnavailable:
            raise HTTPException(409, "当前转人工入口已失效，请使用最新一轮的入口") from None

    @app.get("/api/handoffs/{handoff_id}", response_model=HandoffTicket)
    async def get_handoff(
        handoff_id: str,
        session_id: str,
        buyer: Annotated[str, Depends(require_buyer)],
    ):
        try:
            app.state.agent.sessions.get_or_create(session_id, buyer)
            return app.state.agent.handoffs.get(handoff_id, buyer, session_id)
        except (SessionNotFound, TicketNotFound):
            raise HTTPException(404, "工单不存在") from None

    if evaluations_enabled:

        class EvaluationRequest(BaseModel):
            mode: Literal["offline", "live"] = "offline"

        @app.post("/api/evaluations", status_code=202)
        async def start_evaluation(
            request: EvaluationRequest,
            buyer: Annotated[str, Depends(require_buyer)],
        ):
            try:
                report, reused = await app.state.evaluations.start(request.mode)
                return {"run_id": report["run_id"], "status": report["status"], "reused": reused}
            except ValueError:
                raise HTTPException(409, "真实模型尚未配置，请设置服务端模型配置后再运行") from None
            except RuntimeError:
                raise HTTPException(409, "已有评测正在运行，请等待完成") from None

        @app.get("/api/evaluations/latest")
        async def latest_evaluation(
            buyer: Annotated[str, Depends(require_buyer)],
            mode: Literal["offline", "live"] = "offline",
        ):
            service = app.state.evaluations
            return {"report": service.view(service.latest(mode))}

        @app.get("/api/evaluations/history")
        async def evaluation_history(
            buyer: Annotated[str, Depends(require_buyer)],
            mode: Literal["offline", "live"] = "offline",
        ):
            service = app.state.evaluations
            return {
                "reports": service.history(mode),
                "comparison": service.timeout_comparison() if mode == "live" else None,
            }

        @app.get("/api/evaluations/{run_id}")
        async def get_evaluation(run_id: str, buyer: Annotated[str, Depends(require_buyer)]):
            report = app.state.evaluations.get(run_id)
            if report is None:
                raise HTTPException(404, "评测记录不存在")
            return app.state.evaluations.view(report)

        @app.get("/api/failure-cases")
        async def get_failure_cases(buyer: Annotated[str, Depends(require_buyer)]):
            from evals.service import failure_cases

            return {"cases": failure_cases(), "scope": "历史开发复盘，与本次15条评测成绩分开"}

    return app


app = create_app()
