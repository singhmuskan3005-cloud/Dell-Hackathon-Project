import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models.team import Team
from ..models.participant import Participant

router = APIRouter()


# --------------- Pydantic schemas ---------------

class TeamCreate(BaseModel):
    name: str
    member_ids: Optional[List[str]] = []


class TeamOut(BaseModel):
    team_id: str
    name: Optional[str] = None
    member_ids: Optional[List[str]] = []

    class Config:
        from_attributes = True


class AddMemberRequest(BaseModel):
    participant_id: str


# --------------- CRUD endpoints ---------------

@router.post("/create", response_model=TeamOut)
async def create_team(data: TeamCreate, db: Session = Depends(get_db)):
    """Create a new team."""
    team = Team(
        team_id=uuid.uuid4(),
        name=data.name,
        member_ids=data.member_ids or [],
    )
    db.add(team)
    db.commit()
    db.refresh(team)

    # Update participants with team_id
    for pid in (data.member_ids or []):
        p = db.query(Participant).filter(Participant.id == pid).first()
        if p:
            p.team_id = team.team_id
    db.commit()

    return team


@router.get("/", response_model=List[TeamOut])
async def list_teams(db: Session = Depends(get_db)):
    """List all teams."""
    return db.query(Team).all()


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(team_id: str, db: Session = Depends(get_db)):
    """Get a team by ID."""
    t = db.query(Team).filter(Team.team_id == team_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    return t


@router.post("/{team_id}/add_member", response_model=TeamOut)
async def add_member(team_id: str, data: AddMemberRequest, db: Session = Depends(get_db)):
    """Add a participant to a team."""
    t = db.query(Team).filter(Team.team_id == team_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")

    current_members = list(t.member_ids or [])
    if data.participant_id in current_members:
        raise HTTPException(status_code=409, detail="Participant already in team")

    current_members.append(data.participant_id)
    t.member_ids = current_members

    # Update participant's team_id
    p = db.query(Participant).filter(Participant.id == data.participant_id).first()
    if p:
        p.team_id = t.team_id

    db.commit()
    db.refresh(t)
    return t


@router.delete("/{team_id}")
async def delete_team(team_id: str, db: Session = Depends(get_db)):
    """Delete a team."""
    t = db.query(Team).filter(Team.team_id == team_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")

    # Clear team_id on participants
    for pid in (t.member_ids or []):
        p = db.query(Participant).filter(Participant.id == pid).first()
        if p:
            p.team_id = None

    db.delete(t)
    db.commit()
    return {"detail": "deleted"}


# --------------- Team Formation Invites ---------------

from ..models.invite import Invite, InviteStatus, InviteDirection
from pydantic import BaseModel

class InviteRequest(BaseModel):
    participant_id: str
    leader_id: str

class JoinRequest(BaseModel):
    participant_id: str

class InviteRespondRequest(BaseModel):
    responder_id: str
    accept: bool

@router.post("/{team_id}/invite")
async def invite_participant(team_id: str, data: InviteRequest, db: Session = Depends(get_db)):
    """Leader invites a participant to the team."""
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    try:
        from app.services.ai.core.schemas import Team as TeamSchema
        # Convert to Pydantic schema for the logic
        team_schema = TeamSchema(
            team_id=str(team.team_id),
            name=team.name,
            leader_id=str(team.member_ids[0]) if team.member_ids else None, # Simplified leader logic
            member_ids=[str(m) for m in team.member_ids],
            slots_remaining=max(0, 4 - len(team.member_ids)), # Hardcode 4 max size for now
            is_open=True,
            is_locked=False
        )
        
        from app.services.ai.pipelines.team_formation.invites import invite_participant as ai_invite
        invite_schema = ai_invite(team_schema, data.leader_id, data.participant_id)
        
        new_invite = Invite(
            id=uuid.UUID(invite_schema.invite_id),
            team_id=team.team_id,
            participant_id=data.participant_id,
            direction=InviteDirection.LEADER_TO_PARTICIPANT,
            initiated_by_id=data.leader_id,
            status=InviteStatus.PENDING
        )
        db.add(new_invite)
        db.commit()
        return {"status": "success", "invite_id": str(new_invite.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{team_id}/request-join")
async def request_join(team_id: str, data: JoinRequest, db: Session = Depends(get_db)):
    """Participant requests to join a team."""
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    participant = db.query(Participant).filter(Participant.id == data.participant_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
        
    try:
        from app.services.ai.core.schemas import Team as TeamSchema, Participant as ParticipantSchema
        team_schema = TeamSchema(
            team_id=str(team.team_id),
            name=team.name,
            leader_id=str(team.member_ids[0]) if team.member_ids else None,
            member_ids=[str(m) for m in team.member_ids],
            slots_remaining=max(0, 4 - len(team.member_ids)),
            is_open=True,
            is_locked=False
        )
        participant_schema = ParticipantSchema(
            id=str(participant.id),
            name=participant.name or "",
            college_name=participant.college_name or "",
            skills=[]
        )
        
        from app.services.ai.pipelines.team_formation.invites import request_to_join
        invite_schema = request_to_join(team_schema, participant_schema)
        
        new_invite = Invite(
            id=uuid.UUID(invite_schema.invite_id),
            team_id=team.team_id,
            participant_id=str(participant.id),
            direction=InviteDirection.PARTICIPANT_TO_LEADER,
            initiated_by_id=str(participant.id),
            status=InviteStatus.PENDING
        )
        db.add(new_invite)
        db.commit()
        return {"status": "success", "invite_id": str(new_invite.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/invites/{invite_id}/respond")
async def respond_to_invite(invite_id: str, data: InviteRespondRequest, db: Session = Depends(get_db)):
    """Respond to an invite."""
    invite = db.query(Invite).filter(Invite.id == invite_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
        
    team = db.query(Team).filter(Team.team_id == invite.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    try:
        from app.services.ai.core.schemas import Team as TeamSchema, Invite as InviteSchema
        
        team_schema = TeamSchema(
            team_id=str(team.team_id),
            name=team.name,
            leader_id=str(team.member_ids[0]) if team.member_ids else None,
            member_ids=list(team.member_ids),
            slots_remaining=max(0, 4 - len(team.member_ids)),
            is_open=True,
            is_locked=False
        )
        
        invite_schema = InviteSchema(
            invite_id=str(invite.id),
            team_id=str(invite.team_id),
            participant_id=str(invite.participant_id),
            direction=invite.direction.value,
            initiated_by_id=str(invite.initiated_by_id),
            status=invite.status.value,
            created_at=invite.created_at.isoformat()
        )
        
        from app.services.ai.pipelines.team_formation.invites import respond_to_invite as ai_respond
        updated_inv_schema, updated_team_schema = ai_respond(
            invite=invite_schema,
            responder_id=data.responder_id,
            accept=data.accept,
            team=team_schema
        )
        
        invite.status = InviteStatus(updated_inv_schema.status)
        from datetime import datetime, timezone
        invite.responded_at = datetime.now(timezone.utc)
        
        if updated_team_schema:
            team.member_ids = updated_team_schema.member_ids
            # Update the participant's team_id
            p = db.query(Participant).filter(Participant.id == invite.participant_id).first()
            if p:
                p.team_id = team.team_id
                
        db.commit()
        return {"status": "success", "invite_status": invite.status.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# --------------- AI team formation endpoint ---------------

@router.post("/form")
async def trigger_team_formation(background_tasks: BackgroundTasks):
    """Triggers coverage-driven team assembly as a background task."""
    from app.services.ai.pipelines.team_formation.formation import form_teams
    from app.services.ai.core.schemas import Participant as ParticipantSchema, PSRequirement, SkillVector

    def run_formation():
        from ..deps import SessionLocal
        from ..models.problem_statement import ProblemStatement
        import uuid
        
        db = SessionLocal()
        try:
            # 1. Fetch unassigned participants
            db_participants = db.query(Participant).filter(Participant.team_id == None).all()
            if not db_participants:
                print("No unassigned participants found.")
                return

            schema_participants = []
            for p in db_participants:
                schema_participants.append(
                    ParticipantSchema(
                        id=str(p.id),
                        name=p.name or "Unknown",
                        college_name=p.college_name or "Unknown",
                        github_url=p.github_url or "",
                        skills=p.declared_skills or [],
                        skill_vector=SkillVector.from_dict(p.skill_vector or {})
                    )
                )

            # 2. Fetch problem statements
            db_ps = db.query(ProblemStatement).all()
            if not db_ps:
                print("No problem statements found.")
                return
                
            schema_ps = []
            for ps in db_ps:
                schema_ps.append(
                    PSRequirement(
                        ps_id=str(ps.ps_id),
                        title=ps.title or "Untitled",
                        raw_text=ps.raw_text or "",
                        required_vector=SkillVector.from_dict(ps.required_vector or {}),
                        team_size=ps.max_size or 4
                    )
                )

            # 3. Form teams
            print(f"Starting team formation for {len(schema_participants)} participants and {len(schema_ps)} problem statements...")
            result = form_teams(schema_participants, schema_ps)
            
            formed_teams = result.get("teams", [])
            print(f"Formed {len(formed_teams)} teams.")

            # 4. Save teams to DB
            for t in formed_teams:
                team_id = uuid.uuid4()
                # Use getattr or properties from the Pydantic schema
                member_ids = [m for m in getattr(t, "member_ids", [])] if not hasattr(t, "members") else [m.id for m in getattr(t, "members", [])]
                if not member_ids and hasattr(t, "members"):
                    member_ids = [m.id for m in t.members]
                elif not member_ids:
                    member_ids = t.member_ids
                
                new_team = Team(
                    team_id=team_id,
                    name=f"{t.name}",
                    member_ids=member_ids,
                    coverage_score=getattr(t, "coverage_score", 0.0),
                    diversity_score=getattr(t, "diversity_score", 0.0),
                    formation_confidence=getattr(t, "formation_confidence", 0.0)
                )
                db.add(new_team)
                
                # Update participants
                for p_id in member_ids:
                    db_p = db.query(Participant).filter(Participant.id == p_id).first()
                    if db_p:
                        db_p.team_id = team_id
                        
            db.commit()
            print("Team formation complete and saved to DB.")
            
        except Exception as e:
            print(f"Error in team formation: {e}")
            db.rollback()
        finally:
            db.close()

    background_tasks.add_task(run_formation)
    return {"status": "formation_started", "message": "Teams are being formed in the background."}
