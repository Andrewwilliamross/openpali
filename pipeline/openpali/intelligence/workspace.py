"""Local operational drafts, separate from agency evidence and public releases.

SQLite stores acquisition-task updates and professional claims for local review.
It never substitutes for the canonical PostGIS civic ledger or promotes facts.
"""
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator


class ProjectClaim(BaseModel):
    apn: str = Field(pattern=r'^\d{10}$')
    organization: str = Field(min_length=2,max_length=160)
    role: Literal['owner','general_contractor','framing','architect','engineer','real_estate_agent','other_trade']
    license_number: str | None = Field(default=None,max_length=100)
    scope: str = Field(min_length=10,max_length=1500)
    evidence_url: HttpUrl
    started_at: str | None = Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    ended_at: str | None = Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    sqft: float | None = Field(default=None,gt=0,le=1000000)

    @model_validator(mode='after')
    def dates(self):
        from datetime import date
        for value in (self.started_at,self.ended_at):
            if value:
                d=date.fromisoformat(value)
                if d>datetime.now(timezone.utc).date(): raise ValueError('work dates cannot be in the future')
        if self.ended_at and (not self.started_at or self.ended_at<self.started_at):
            raise ValueError('completion requires an earlier start date')
        return self


class TaskUpdate(BaseModel):
    status: Literal['queued','in_progress','needs_review']
    note: str = Field(min_length=5,max_length=2000)
    evidence_url: HttpUrl | None = None


class Workspace:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, kind TEXT NOT NULL, subject TEXT NOT NULL, release_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)')
            conn.execute('CREATE INDEX IF NOT EXISTS events_subject ON events(kind,subject)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def append(self,kind,subject,release_id,payload):
        event=dict(id=uuid4().hex,kind=kind,subject=subject,release_id=release_id,
                   created_at=datetime.now(timezone.utc).isoformat(),payload=payload)
        with self.connect() as conn:
            conn.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',(event['id'],kind,subject,release_id,event['created_at'],json.dumps(payload)))
        return event

    def list(self,kind,subject):
        with self.connect() as conn:
            rows=conn.execute('SELECT id,release_id,created_at,payload FROM events WHERE kind=? AND subject=? ORDER BY created_at',(kind,subject)).fetchall()
        return [dict(id=r[0],release_id=r[1],created_at=r[2],payload=json.loads(r[3])) for r in rows]
