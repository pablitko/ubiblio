from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .. import isbn_import, photo_import
from .. import vars as env
from ..database import SessionLocal
from ..dependencies import CHUNK_SIZE, admin_user, get_rate_limiter, templates
from ..vars import METADATA_DELAY_S
from .books import service
from .books.vision_client import GeminiVisionClient, prepare_image

router = APIRouter()

MAX_ISBNS_PER_JOB = 1000


def run_isbn_job(job):
    isbn_import.run_job(job, SessionLocal, service.lookup_book_metadata_by_isbn, delay=METADATA_DELAY_S)


# --------------------------------------------------------------------------
# Bulk ISBN import
# --------------------------------------------------------------------------
@router.get("/import_isbn", dependencies=[get_rate_limiter(times=3, seconds=2)], response_class=HTMLResponse)
def import_isbn_form(request: Request, user: admin_user):
    context = {"request": request, "user": user, "errors": []}
    return templates.TemplateResponse(request, "importIsbn.html", context)


@router.post("/import_isbn", dependencies=[get_rate_limiter(times=1, seconds=2)], response_class=HTMLResponse)
async def import_isbn_post(
        request: Request,
        user: admin_user,
        background_tasks: BackgroundTasks,
        isbns: str = Form(""),
        file: UploadFile | None = File(None),
        library: str = Form(""),
        shelf: str = Form(""),
        collection: str = Form("")):
    items = isbn_import.parse_isbn_input(isbns)
    if file is not None and file.filename:
        try:
            items += isbn_import.parse_isbn_input((await file.read()).decode("utf-8-sig"))
        except UnicodeDecodeError:
            context = {"request": request, "user": user, "errors": ["The file is not UTF-8 encoded."]}
            return templates.TemplateResponse(request, "importIsbn.html", context)
    errors = []
    if not items:
        errors.append("No ISBNs given.")
    if len(items) > MAX_ISBNS_PER_JOB:
        errors.append(f"Too many ISBNs ({len(items)}); the limit is {MAX_ISBNS_PER_JOB} per import.")
    if errors:
        context = {"request": request, "user": user, "errors": errors}
        return templates.TemplateResponse(request, "importIsbn.html", context)
    job = isbn_import.create_job(items, library.strip(), shelf.strip(), collection.strip())
    background_tasks.add_task(run_isbn_job, job)
    return RedirectResponse(url=f"/import_isbn/job/{job.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/import_isbn/job/{job_id}", response_class=HTMLResponse)
def import_isbn_job_page(job_id: str, request: Request, user: admin_user):
    job = isbn_import.JOBS.get(job_id)
    if job is None:
        return HTMLResponse("Import job not found (jobs are lost when the server restarts).", status_code=404)
    context = {"request": request, "user": user, "job": job}
    return templates.TemplateResponse(request, "importIsbnJob.html", context)


@router.get("/import_isbn/status/{job_id}")
def import_isbn_status(job_id: str, user: admin_user):
    job = isbn_import.JOBS.get(job_id)
    if job is None:
        return JSONResponse({"detail": "job not found"}, status_code=404)
    return job.to_dict()


@router.get("/import_isbn/report/{job_id}")
def import_isbn_report(job_id: str, user: admin_user):
    job = isbn_import.JOBS.get(job_id)
    if job is None:
        return JSONResponse({"detail": "job not found"}, status_code=404)
    filename = "isbnImport" + job.created.strftime("%m_%d_%Y_%H_%M_%S") + ".csv"
    return Response(
        isbn_import.report_csv(job).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------
# Continuous scanning: one barcode -> one saved book, JSON in and out
# --------------------------------------------------------------------------
class ScanAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    isbn: str = Field(max_length=32)
    library: str = Field(default="", max_length=200)
    shelf: str = Field(default="", max_length=200)
    collection: str = Field(default="", max_length=200)


@router.post("/api/scan_add", dependencies=[get_rate_limiter(times=5, seconds=1)])
def scan_add(body: ScanAdd, user: admin_user):
    db = SessionLocal()
    try:
        known = isbn_import.existing_isbns(db)
        result = isbn_import.add_book_by_isbn(
            db, body.isbn, known, service.lookup_book_metadata_by_isbn,
            body.library.strip(), body.shelf.strip(), body.collection.strip())
    finally:
        db.close()
    return {key: result.get(key) for key in ("status", "isbn", "title", "author", "bookId", "error")}


# --------------------------------------------------------------------------
# Shelf photo import (Gemini); candidates are saved only after approval
# --------------------------------------------------------------------------
def photo_import_enabled():
    return bool(env.GEMINI_API_KEY and env.GEMINI_MODEL)


def run_photo_job(job):
    client = GeminiVisionClient(env.GEMINI_API_KEY, env.GEMINI_MODEL)
    photo_import.run_job(job, client, SessionLocal, delay=env.PHOTO_IMPORT_DELAY_S)


def photo_form(request, user, errors=None):
    context = {
        "request": request, "user": user, "errors": errors or [],
        "enabled": photo_import_enabled(),
        "maxImages": env.PHOTO_IMPORT_MAX_IMAGES, "maxMb": env.PHOTO_IMPORT_MAX_MB,
    }
    return templates.TemplateResponse(request, "importPhotos.html", context)


async def read_limited(file: UploadFile, max_bytes: int) -> bytes | None:
    """File contents, or None if it is larger than max_bytes."""
    data = bytearray()
    while chunk := await file.read(CHUNK_SIZE):
        data += chunk
        if len(data) > max_bytes:
            return None
    return bytes(data)


@router.get("/import_photos", dependencies=[get_rate_limiter(times=3, seconds=2)], response_class=HTMLResponse)
def import_photos_form(request: Request, user: admin_user):
    return photo_form(request, user)


@router.post("/import_photos", dependencies=[get_rate_limiter(times=1, seconds=2)], response_class=HTMLResponse)
async def import_photos_post(
        request: Request,
        user: admin_user,
        background_tasks: BackgroundTasks,
        files: list[UploadFile] = File([]),
        library: str = Form(""),
        shelf: str = Form(""),
        collection: str = Form("")):
    if not photo_import_enabled():
        return photo_form(request, user, ["Photo import is disabled: set GEMINI_API_KEY and GEMINI_MODEL."])
    files = [f for f in files if f.filename]
    if not files:
        return photo_form(request, user, ["No photos given."])
    if len(files) > env.PHOTO_IMPORT_MAX_IMAGES:
        return photo_form(request, user, [f"Too many photos ({len(files)}); the limit is {env.PHOTO_IMPORT_MAX_IMAGES}."])
    images, names, errors = [], [], []
    for file in files:
        data = await read_limited(file, int(env.PHOTO_IMPORT_MAX_MB * 1024 * 1024))
        if data is None:
            errors.append(f"{file.filename}: larger than {env.PHOTO_IMPORT_MAX_MB:g} MB.")
            continue
        try:
            images.append(prepare_image(data))
            names.append(file.filename)
        except ValueError:
            errors.append(f"{file.filename}: not a supported image.")
    if errors:
        return photo_form(request, user, errors)
    job = photo_import.create_job(images, names, library.strip(), shelf.strip(), collection.strip())
    background_tasks.add_task(run_photo_job, job)
    return RedirectResponse(url=f"/import_photos/job/{job.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/import_photos/job/{job_id}", response_class=HTMLResponse)
def import_photos_job_page(job_id: str, request: Request, user: admin_user, saved: int | None = None):
    job = photo_import.JOBS.get(job_id)
    if job is None:
        return HTMLResponse("Import job not found (jobs are lost when the server restarts).", status_code=404)
    context = {"request": request, "user": user, "job": job, "saved": saved}
    return templates.TemplateResponse(request, "importPhotosJob.html", context)


@router.get("/import_photos/status/{job_id}")
def import_photos_status(job_id: str, user: admin_user):
    job = photo_import.JOBS.get(job_id)
    if job is None:
        return JSONResponse({"detail": "job not found"}, status_code=404)
    return job.to_dict()


@router.post("/import_photos/job/{job_id}/resume")
def import_photos_resume(job_id: str, user: admin_user, background_tasks: BackgroundTasks):
    job = photo_import.JOBS.get(job_id)
    if job is None:
        return JSONResponse({"detail": "job not found"}, status_code=404)
    if job.state in ("paused", "failed"):
        job.state = "queued"
        background_tasks.add_task(run_photo_job, job)
    return RedirectResponse(url=f"/import_photos/job/{job.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/import_photos/job/{job_id}/save")
async def import_photos_save(job_id: str, request: Request, user: admin_user):
    job = photo_import.JOBS.get(job_id)
    if job is None:
        return JSONResponse({"detail": "job not found"}, status_code=404)
    form = await request.form()
    approved = {}
    for key in form.keys():
        if key.startswith("save_"):
            try:
                index = int(key[len("save_"):])
            except ValueError:
                continue
            approved[index] = (str(form.get(f"title_{index}", "")), str(form.get(f"author_{index}", "")))
    db = SessionLocal()
    try:
        saved = photo_import.save_candidates(db, job, approved)
    finally:
        db.close()
    return RedirectResponse(url=f"/import_photos/job/{job.id}?saved={saved}", status_code=status.HTTP_303_SEE_OTHER)


# --------------------------------------------------------------------------
# Books that still need manual completion
# --------------------------------------------------------------------------
@router.get("/to_complete", dependencies=[get_rate_limiter(times=3, seconds=2)], response_class=HTMLResponse)
def to_complete_page(request: Request, user: admin_user):
    db = SessionLocal()
    try:
        books = isbn_import.books_to_complete(db)
    finally:
        db.close()
    context = {"request": request, "user": user, "books": books}
    return templates.TemplateResponse(request, "toComplete.html", context)
