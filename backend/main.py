import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mock_jobs import router as mock_jobs_router

load_dotenv()

# Frontend URLs allowed to call this API from the browser (comma-separated).
FRONTEND_ORIGINS = (os.getenv("FRONTEND_ORIGINS") or "http://localhost:3000").split(",")

app = FastAPI(title="AI-voice2text backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in FRONTEND_ORIGINS if origin.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(mock_jobs_router)


@app.get("/")
def root():
    return {"message": "AI-voice2text backend is running"}


@app.get("/health")
def health():
    return {"status": "ok"}
