from fastapi import APIRouter, HTTPException, status

from app.schemas.job import JobAccepted
from app.schemas.review import Review
from app.services import jobs

router = APIRouter(prefix="/review", tags=["reviews"])


# Manual endpoint (handy for testing without WhatsApp)
@router.post("/", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
def submit_review(review: Review):
    job_id = jobs.enqueue_review(review.review, review.created_at.isoformat(), source="manual")
    return JobAccepted(job_id=job_id, status="queued")


# NOTE: must be declared before /{job_id}, otherwise "latest" is treated as an id
@router.get("/latest")
def get_latest():
    job_id = jobs.get_latest_job_id()
    if job_id is None:
        raise HTTPException(status_code=404, detail="No jobs yet")
    body = jobs.get_job(job_id) or {"status": "expired"}
    return {"job_id": job_id, **body}


@router.get("/{job_id}")
def get_result(job_id: str):
    data = jobs.get_job(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return data
