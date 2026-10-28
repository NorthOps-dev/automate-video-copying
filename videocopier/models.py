from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CaptionMode = Literal["client", "auto", "reference", "footage"]
SlotStatus = Literal["filled", "unfilled"]
JobStatus = Literal["queued", "running", "review", "done", "error"]


class Word(BaseModel):
    text: str
    start: float
    end: float


class CaptionLine(BaseModel):
    text: str
    start: float
    end: float
    words: list[Word] = Field(default_factory=list)
    kind: str = "speech"
    y_ratio: float = 0.22
    # Copied from the working TikTok: classic = white fill + black outline;
    # box = dark type on a white rounded pill.
    face: str = "classic"
    width_ratio: float = 0.0
    size_ratio: float = 0.0


class Shot(BaseModel):
    index: int
    start: float
    end: float
    duration: float
    role: str = "broll"
    motion: str = "gentle"
    energy: float = 0.0
    mean_luma: float = 0.5
    saturation: float = 0.4
    has_face: bool = False
    transcript: str = ""
    embedding: list[float] = Field(default_factory=list)


class Blueprint(BaseModel):
    path: str
    duration: float
    width: int
    height: int
    fps: float
    bpm: float | None = None
    beats: list[float] = Field(default_factory=list)
    transcript: str = ""
    captions: list[CaptionLine] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)


class Scene(BaseModel):
    path: str
    start: float
    end: float
    duration: float
    quality: float = 0.5
    motion: str = "gentle"
    energy: float = 0.0
    has_face: bool = False
    face_x: float = 0.5
    mean_luma: float = 0.5
    embedding: list[float] = Field(default_factory=list)


class FootageIndex(BaseModel):
    scenes: list[Scene] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    durations: dict[str, float] = Field(default_factory=dict)


class Slot(BaseModel):
    shot_index: int
    start: float
    end: float
    duration: float
    role: str
    status: SlotStatus
    score: float = 0.0
    reason: str = ""
    source_path: str | None = None
    source_in: float | None = None
    source_out: float | None = None
    speed: float = 1.0
    face_x: float = 0.5


class CutList(BaseModel):
    duration: float
    slots: list[Slot]
    unfilled: list[str] = Field(default_factory=list)


class JobSpec(BaseModel):
    reference: str
    footage: str = ""
    footage_paths: list[str] = Field(default_factory=list)
    music: str | None = None
    caption_mode: CaptionMode = "client"
    match_threshold: float = 0.08
    client_id: str = ""


class JobState(BaseModel):
    id: str
    status: JobStatus = "queued"
    step: str = "queued"
    log: list[str] = Field(default_factory=list)
    spec: JobSpec
    error: str | None = None
    output_mp4: str | None = None
    output_xml: str | None = None
    output_cutlist: str | None = None
    unfilled: list[str] = Field(default_factory=list)
    source_captions: list[CaptionLine] = Field(default_factory=list)
    draft_captions: list[CaptionLine] = Field(default_factory=list)
