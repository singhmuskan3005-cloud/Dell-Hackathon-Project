from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid

from ..database import execute, fetch_all
from ..worker import detect_bias_task

router = APIRouter()

class EvaluationSubmitRequest(BaseModel):
    hackathon_id: str
    assignment_id: str
    reviewer_id: str
    idea_id: str
    score: float
    feedback: Optional[str] = None

class BiasReportResponse(BaseModel):
    alerts: List[dict]

@router.post("/submit")
async def submit_evaluation(request: EvaluationSubmitRequest):
    """
    Submits a new evaluation score and triggers the background bias detection task.
    """
    eval_id = str(uuid.uuid4())
    
    query = """
    INSERT INTO evaluations (evaluation_id, assignment_id, reviewer_id, idea_id, score, feedback, created_at)
    VALUES (%s, %s, %s, %s, %s, %s, NOW())
    """
    try:
        execute(query, (
            eval_id,
            request.assignment_id,
            request.reviewer_id,
            request.idea_id,
            request.score,
            request.feedback
        ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit evaluation: {str(e)}")

    # Trigger background bias detection
    detect_bias_task.delay(request.hackathon_id)

    return {"status": "success", "evaluation_id": eval_id}


@router.get("/bias-report", response_model=BiasReportResponse)
async def get_bias_report():
    """
    Fetches the latest BIAS_ALERT logs from the audit_logs table.
    """
    query = """
    SELECT payload, created_at
    FROM audit_logs
    WHERE event_type = 'BIAS_ALERT'
    ORDER BY created_at DESC
    LIMIT 50
    """
    try:
        results = fetch_all(query)
        alerts = []
        for r in results:
            alert = r['payload']
            alert['created_at'] = r['created_at']
            alerts.append(alert)
        return {"alerts": alerts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch bias report: {str(e)}")
