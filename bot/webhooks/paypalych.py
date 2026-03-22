import logging

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from bot.services import payment_service

logger = logging.getLogger(__name__)


def build_webhook_app(bot):
    app = FastAPI(title="XantheShop PayPalych webhooks")

    @app.get("/health")
    async def health() -> dict:
        """Проверка доступности HTTP-сервера (Docker / балансировщик)."""
        return {"status": "ok"}

    @app.post("/webhooks/paypalych/result", response_class=PlainTextResponse)
    async def paypalych_result(request: Request):
        form = await request.form()
        payload = dict(form)
        # Логируем без SignatureValue (секрет не пишем в лог целиком при необходимости)
        logger.info(
            "PayPalych Result URL: Status=%s InvId=%s TrsId=%s OutSum=%s custom=%s",
            payload.get("Status"),
            payload.get("InvId"),
            payload.get("TrsId"),
            payload.get("OutSum"),
            payload.get("custom"),
        )
        result = await payment_service.process_paypalych_postback(payload, bot)
        return result

    return app

