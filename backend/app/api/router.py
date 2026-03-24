from fastapi import APIRouter

from app.api.routes import agent, audit, auth, broker, config, decisions, goals, health, market, news, orders, portfolio, scheduler, strategy


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(agent.router)
api_router.include_router(config.router)
api_router.include_router(goals.router)
api_router.include_router(strategy.router)
api_router.include_router(broker.router)
api_router.include_router(decisions.router)
api_router.include_router(orders.router)
api_router.include_router(portfolio.router)
api_router.include_router(market.router)
api_router.include_router(news.router)
api_router.include_router(scheduler.router)
api_router.include_router(audit.router)
api_router.include_router(health.router)
