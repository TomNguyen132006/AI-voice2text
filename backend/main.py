from fastapi import FastAPI

from mock_jobs import router as mock_jobs_router

app = FastAPI(title="AI-voice2text backend")
app.include_router(mock_jobs_router)


@app.get("/")
def root():
    return {"message": "AI-voice2text backend is running"}


@app.get("/health")
def health():
    return {"status": "ok"}
