"""Cloud entry point: password-protected demo, one worker, runtime-only secrets."""

import base64
import binascii
import os
import secrets

import uvicorn
from starlette.responses import JSONResponse, Response

from aftersales.main import create_app


class DemoAccess:
    def __init__(self, app, username: str, password: str):
        self.app = app
        self.expected = f"{username}:{password}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["path"] == "/healthz" and scope["method"] in ("GET", "HEAD"):
            await JSONResponse({"status": "ok"})(scope, receive, send)
            return
        authorization = dict(scope["headers"]).get(b"authorization", b"")
        scheme, _, token = authorization.partition(b" ")
        try:
            supplied = base64.b64decode(token, validate=True) if scheme.lower() == b"basic" else b""
        except (binascii.Error, ValueError):
            supplied = b""
        if not secrets.compare_digest(supplied, self.expected):
            await Response(
                "需要演示访问凭据",
                status_code=401,
                headers={
                    "WWW-Authenticate": 'Basic realm="Aftersales Demo", charset="UTF-8"',
                    "Cache-Control": "no-store",
                },
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_hosted_app():
    username = os.getenv("DEMO_ACCESS_USERNAME", "demo")
    password = os.getenv("DEMO_ACCESS_PASSWORD", "")
    if not username or ":" in username or len(password) < 16:
        raise ValueError("部署需设置有效演示用户名及至少16位的 DEMO_ACCESS_PASSWORD")
    mode = os.getenv("AGENT_MODE", "live")
    if mode == "live":
        key = os.getenv("QIANFAN_API_KEY", "").strip()
        if not key or key == "replace-with-your-key":
            raise ValueError("真实模式部署需设置千帆 QIANFAN_API_KEY")
        os.environ.update(
            MODEL_NAME="openai/ernie-5.1",
            MODEL_BASE_URL="https://qianfan.baidubce.com/v2",
            MODEL_API_KEY=key,
            MODEL_TRANSPORT="litellm",
            LITELLM_LOCAL_MODEL_COST_MAP="True",
        )
    return DemoAccess(create_app(mode_override=mode), username, password)


if __name__ == "__main__":
    uvicorn.run(
        "aftersales.hosting:create_hosted_app",
        factory=True,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        workers=1,
    )
