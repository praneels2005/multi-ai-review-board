from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.middleware import RequestLoggingMiddleware
from app.schemas import IdeaInput, ValidationResponse
from app.services.validation_service import run_validation
from app.utils.validators import sanitize_idea, validate_idea_length
from app.api.review_board_router import router as review_board_router

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Multiple AI Review Board",
    description="Multi-agent startup idea review board with bespoke specialist panels, debate rounds, and coordinator synthesis.",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Review Board Router
app.include_router(review_board_router)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please slow down."})

@app.get("/health")
def health():
    return {"status": "ok", "service": "multiple-ai-review-board", "version": "1.0.0"}

@app.post("/validate-idea", response_model=ValidationResponse)
@limiter.limit("10/minute")
async def validate_idea(request: Request, body: IdeaInput):
    try:
        idea = sanitize_idea(body.idea)
        idea = validate_idea_length(idea)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        result = run_validation(idea)
        return ValidationResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Validation failed. Please try again.")
