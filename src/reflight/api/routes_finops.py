from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from reflight.api.deps import get_db, require_api_key
from reflight.finops.report import build_report, render_markdown

router = APIRouter(prefix="/runs", tags=["finops"], dependencies=[Depends(require_api_key)])


@router.get("/{run_id}/finops")
def get_finops(
    run_id: str,
    profile: str | None = None,
    format: str = "json",
    db: Session = Depends(get_db),
):
    try:
        report = build_report(db, run_id, profile)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if format == "markdown":
        return Response(content=render_markdown(report), media_type="text/markdown")
    return report
