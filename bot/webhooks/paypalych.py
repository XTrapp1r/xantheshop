from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from bot.services import payment_service


def build_webhook_app(bot):
    app = FastAPI()

    @app.post("/webhooks/paypalych/result", response_class=PlainTextResponse)
    async def paypalych_result(request: Request):
        form = await request.form()
        payload = dict(form)
        result = await payment_service.process_paypalych_postback(payload, bot)
        return result

    return app

