import logging

from fastapi import FastAPI, Request, Response, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
from fastapi_limiter import FastAPILimiter

from . import models
from .database import engine
from .dependencies import templates
from .vars import USE_REDIS, REDIS_URL

from .routers import auth, books, reading_lists, files, admin, federation, imports, api_v1

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=False,
    allow_methods=['POST'],
    allow_headers=['*']
)


@app.middleware("http")
async def head_as_get(request: Request, call_next):
    if request.method != "HEAD":
        return await call_next(request)
    request.scope["method"] = "GET"
    response = await call_next(request)
    return Response(
        status_code=response.status_code,
        headers=dict[str, str](response.headers),
        content=b"",
    )


api_log = logging.getLogger("ubiblio.api")
api_log.setLevel(logging.INFO)
if not api_log.handlers:
    api_log.addHandler(logging.StreamHandler())


@app.middleware("http")
async def log_api_calls(request: Request, call_next):
    #One line per /api/v1 call: token name (never the token), method, path, status
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/"):
        api_log.info("api token=%s %s %s -> %s", getattr(request.state, "api_token_name", "-"),
                     request.method, request.url.path, response.status_code)
    return response


@app.on_event("startup")
async def startup():
    if USE_REDIS:
        redis_connection = redis.from_url(
            REDIS_URL, encoding="utf-8", decode_responses=True)
        await FastAPILimiter.init(redis_connection)


app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(books.router)
app.include_router(reading_lists.router)
app.include_router(files.router)
app.include_router(federation.router)
app.include_router(imports.router)
app.include_router(api_v1.router)
