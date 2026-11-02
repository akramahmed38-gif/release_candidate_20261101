
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

EXAM_LEVEL_VALUES = ("Entry Level", "Professional Level", "Expert Level")
DEFAULT_EXAM_LEVEL = EXAM_LEVEL_VALUES[0]
ExamLevelValue = Literal["Entry Level", "Professional Level", "Expert Level"]

class ChoicePayload(BaseModel):
    choice_text: str
    is_correct: bool = False

class QuestionPayload(BaseModel):
    question_text: str
    question_type: Literal["MCQ", "TF", "Essay"]
    points: int = Field(default=1, ge=1)
    question_group: Optional[str] = None
    choices: Optional[List[ChoicePayload]] = None  # required for MCQ/TF


class QuestionBankCreatePayload(QuestionPayload):
    is_favorite: bool = False


class QuestionBankUpdatePayload(QuestionPayload):
    is_favorite: bool = False

class AudienceFilters(BaseModel):
    hr_ids: List[str] = Field(default_factory=list)
    titles: List[str] = Field(default_factory=list)
    branch_codes: List[str] = Field(default_factory=list)
    branches: List[str] = Field(default_factory=list)
    areas: List[str] = Field(default_factory=list)
    regions: List[str] = Field(default_factory=list)
    divisions: List[str] = Field(default_factory=list)
    departments: List[str] = Field(default_factory=list)
    sub_departments: List[str] = Field(default_factory=list)

class AudiencePayload(BaseModel):
    mode: Literal["all", "filters", "manual"] = "all"
    filters: AudienceFilters = Field(default_factory=AudienceFilters)
    manual_hr_ids: List[str] = Field(default_factory=list)


class ExamPayloadBase(BaseModel):
    title: str
    description: str
    exam_status: str
    exam_level: ExamLevelValue = DEFAULT_EXAM_LEVEL
    duration_minutes: int
    passing_percent: float = Field(default=60.0, ge=0, le=100)
    number_of_attempts_allowed: Optional[int] = Field(default=1, ge=1, le=5)
    start_date: datetime
    end_date: datetime
    material_ids: List[str] = Field(default_factory=list)
    questions: List[QuestionPayload] = Field(default_factory=list)
    audience: AudiencePayload = Field(default_factory=AudiencePayload)
    audience_update_mode: Literal["replace", "append"] = "replace"
    
    @field_validator('end_date')
    @classmethod
    def validate_end_after_start(cls, v: datetime, info) -> datetime:
        """Validate that end_date is after start_date"""
        start_date = info.data.get('start_date')
        if start_date and v < start_date:
            raise ValueError('end_date must be after start_date')
        return v


class ExamCreatePayload(ExamPayloadBase):
    """Create payload with no past-date restriction for exam start time."""


class ExamUpdatePayload(ExamPayloadBase):
    """Updates remain flexible so HR can adjust existing exams after they start."""


class ExamLevelUpdatePayload(BaseModel):
    exam_level: ExamLevelValue


class ExamAnswerSubmission(BaseModel):
    question_id: str
    choice_id: Optional[str] = None
    choice_ids: Optional[List[str]] = None


class ExamSubmitPayload(BaseModel):
    answers: List[ExamAnswerSubmission] = Field(default_factory=list)


class EmployeePerformanceListPayload(BaseModel):
    filters: AudienceFilters = Field(default_factory=AudienceFilters)
    period: Literal["all", "week", "month", "year"] = "all"
    exams_joined: Optional[int] = Field(default=None, ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    sort_by: Literal["hr_id", "name", "branch_code", "exams_joined", "average_percentage"] = "average_percentage"
    sort_dir: Literal["asc", "desc"] = "desc"


class EmployeePerformanceExportPayload(BaseModel):
    filters: AudienceFilters = Field(default_factory=AudienceFilters)
    period: Literal["all", "week", "month", "year"] = "all"
    exams_joined: Optional[int] = Field(default=None, ge=0)
    sort_by: Literal["hr_id", "name", "branch_code", "exams_joined", "average_percentage"] = "average_percentage"
    sort_dir: Literal["asc", "desc"] = "desc"
