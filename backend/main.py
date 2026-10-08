from fastapi import FastAPI

app = FastAPI(title="AI-voice2text backend")


@app.get("/")
def root():
    return {"message": "AI-voice2text backend is running"}
