from fastapi import FastAPI
from mangum import Mangum
from fastapi.middleware.cors import CORSMiddleware

from settings_v1 import settings
import auth_router
import chat_router
import conversation_router
import events_router
import user_preferences_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API service to handle user chat prompts and orchestrate LLM calls and tool execution.",
    root_path=f"{settings.API_V1_STR}"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(chat_router.router)
app.include_router(conversation_router.router)
app.include_router(events_router.router)
app.include_router(user_preferences_router.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "message": f"Welcome to {settings.PROJECT_NAME}"}


lambda_handler = Mangum(app, lifespan="off")
