"""Routes anyone can call: health, the model card, and the website's 'request a pilot' form."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DB
from . import __version__, db as M, engine
from .config import get_settings
from .deps import client_ip
from .security import EMAIL, limiter

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    i = engine.info()
    return {"status": i["status"], "app_version": __version__, "app_name": get_settings().app_name, "engine_tag": i["engine_tag"], "engine_commit": i["engine_commit"],
            "channels": i["channels"], "not_assessed_channels": i["not_assessed_channels"], "window_minutes": i["window_minutes"], "alert_line": i["alert_line"],
            "correlation_trained_on": i["fusion_trained_on"]}


@router.get("/public/model-card")
def model_card():
    return engine.model_card()


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    organisation: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=4000)
    website: str = Field(default="", max_length=200)          # a field people never see: bots fill it


@router.post("/public/contact")
def contact(body: ContactIn, request: Request, db: DB = Depends(M.get_db)):
    if not limiter.allow(f"contact:{client_ip(request)}", 5, 3600): raise HTTPException(429, "too many messages from this address: try again later")
    if body.website: return {"ok": True}
    if not EMAIL.match(body.email.strip()): raise HTTPException(422, "that email address does not look right")
    db.add(M.Lead(name=body.name.strip(), email=body.email.strip(), organisation=body.organisation.strip(), message=body.message.strip())); db.commit()
    return {"ok": True}
