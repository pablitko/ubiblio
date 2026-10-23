from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .. import isbn_import
from ..database import SessionLocal
from ..dependencies import admin_user, get_rate_limiter, templates
from ..vars import METADATA_DELAY_S
from .books import service

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
