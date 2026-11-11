"""Company profile endpoints (CRUD)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CompanyProfile
from app.db.session import get_session
from app.eligibility.profile import CompanyProfileData

router = APIRouter(prefix="/profiles", tags=["profiles"])

SessionDep = Annotated[Session, Depends(get_session)]


class CompanyProfileRead(CompanyProfileData):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


def to_read(profile: CompanyProfile) -> CompanyProfileRead:
    return CompanyProfileRead(
        **profile.data,
        id=profile.id,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def get_profile_or_404(session: Session, profile_id: uuid.UUID) -> CompanyProfile:
    profile = session.get(CompanyProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perfil não encontrado.")
    return profile


@router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(body: CompanyProfileData, session: SessionDep) -> CompanyProfileRead:
    profile = CompanyProfile(name=body.name, data=body.model_dump(mode="json"))
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return to_read(profile)


@router.get("")
def list_profiles(session: SessionDep) -> list[CompanyProfileRead]:
    profiles = session.scalars(select(CompanyProfile).order_by(CompanyProfile.name))
    return [to_read(profile) for profile in profiles]


@router.get("/{profile_id}")
def get_profile(profile_id: uuid.UUID, session: SessionDep) -> CompanyProfileRead:
    return to_read(get_profile_or_404(session, profile_id))


@router.put("/{profile_id}")
def replace_profile(
    profile_id: uuid.UUID, body: CompanyProfileData, session: SessionDep
) -> CompanyProfileRead:
    profile = get_profile_or_404(session, profile_id)
    profile.name = body.name
    profile.data = body.model_dump(mode="json")
    session.commit()
    session.refresh(profile)
    return to_read(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: uuid.UUID, session: SessionDep) -> Response:
    """Earlier eligibility checks are kept, with the profile as it was then."""
    session.delete(get_profile_or_404(session, profile_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
