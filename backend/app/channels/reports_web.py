"""Serves the generated PDF for a report — only after consent has been
recorded (see app/agents/report_delivery_agent.py). No auth beyond that:
this is a local-prototype download link, not something exposed publicly.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.db import SessionLocal
from app.models import Report

router = APIRouter()


@router.get("/reports/{report_id}/download")
def download_report(report_id: int) -> FileResponse:
    db = SessionLocal()
    try:
        report = db.get(Report, report_id)
        if report is None or report.consent_at is None:
            raise HTTPException(status_code=404, detail="Report not found or not yet released")

        path = Path(report.file_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Report file missing on disk")

        return FileResponse(path, media_type="application/pdf", filename=path.name)
    finally:
        db.close()
