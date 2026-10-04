"""Lecture analysis for the session owner (never part of share links)."""

from fastapi import APIRouter

from sonora.api.deps import DB, CurrentUser, OwnedSession, ServicesDep
from sonora.api.schemas import AnalysisOut
from sonora.models import AnalysisStatus, SessionAnalysis
from sonora.services import analysis as analysis_service

router = APIRouter(prefix="/sessions/{session_id}/analysis", tags=["analysis"])


def _out(analysis: SessionAnalysis | None) -> AnalysisOut:
    if analysis is None:
        return AnalysisOut(status="none")
    result = analysis.result if analysis.status is AnalysisStatus.READY else None
    return AnalysisOut(
        status=analysis.status.value,
        error_message=analysis.error_message,
        model=analysis.model,
        completed_at=analysis.completed_at,
        scores=result.get("scores") if result else None,
        topics=result.get("topics") if result else None,
        metrics=result.get("metrics") if result else None,
    )


@router.get("", response_model=AnalysisOut)
async def get_analysis(session: OwnedSession, db: DB) -> AnalysisOut:
    return _out(await analysis_service.get(db, session))


@router.post("", status_code=202, response_model=AnalysisOut)
async def request_analysis(
    session: OwnedSession, user: CurrentUser, db: DB, services: ServicesDep
) -> AnalysisOut:
    """Queues the analysis of a session that has none yet (or whose analysis failed)."""
    return _out(await analysis_service.request(db, services, user, session))
