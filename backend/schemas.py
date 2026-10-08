"""Shared data contracts for the whole pipeline (S0-7).

Every step reads and writes these shapes, so different people can build
different steps at the same time and they still fit together.

Conventions:
- All ids are strings, e.g. "seg_0001", "sec_01", "st_0001".
- All times are seconds from the start of the recording (float), e.g. 75.5 = 01:15.5.

Changes to this file after Oct 11 must be announced to the team.
"""
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """One piece of the transcript, with its time range in the recording."""

    id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class Section(BaseModel):
    """One topic of the lecture: a group of consecutive segments."""

    id: str
    title: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    segment_ids: list[str]


class LectureSource(BaseModel):
    """A statement is supported by a moment in the lecture."""

    type: Literal["lecture"] = "lecture"
    segment_id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class WebSource(BaseModel):
    """A statement is supported by a web page found by our own search."""

    type: Literal["web"] = "web"
    url: str  # kept as plain text so it can be compared exactly with search results
    title: str = ""


# A source is EITHER a lecture timestamp OR a web link; "type" tells which one.
Source = Annotated[Union[LectureSource, WebSource], Field(discriminator="type")]


class Statement(BaseModel):
    """One point in the notes or slides, with the sources that back it up.

    sources may be empty here on purpose: the judge (S5-2) must be able to
    receive a statement with no source and reject it.
    """

    id: str
    section_id: str
    text: str
    sources: list[Source] = []


class Slide(BaseModel):
    section_id: str
    title: str
    bullets: list[Statement]
    example: Optional[str] = None
    speaker_notes: str = ""


JobStatus = Literal["queued", "running", "done", "error"]
JobStage = Literal[
    "queued",
    "transcribing",
    "cleaning",
    "enriching",
    "writing",
    "judging",
    "exporting",
    "done",
]


class JobOutputs(BaseModel):
    """Download links for the finished files (None until they exist)."""

    txt: Optional[str] = None
    md: Optional[str] = None
    pptx: Optional[str] = None


class Job(BaseModel):
    id: str
    status: JobStatus
    stage: JobStage
    error: Optional[str] = None
    outputs: JobOutputs = JobOutputs()


class JobResponse(Job):
    """What GET /jobs/{id} returns: the Job, plus the statements once it is done."""

    statements: list[Statement] = []
