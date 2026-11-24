from fastapi import FastAPI

from api import health


def create_app() -> FastAPI:
    app = FastAPI(title="ShopSense API")
    app.include_router(health.router)
    return app


app = create_app()
