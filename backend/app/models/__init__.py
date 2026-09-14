"""Expose all ORM models from a single import point."""
from app.models.experience import (
    CareerGoal,
    EducationExp,
    Interest,
    InternshipExp,
    ProjectExp,
    Skill,
    WorkPreference,
)
from app.models.explore import (
    Direction,
    DirectionRecommendation,
    ExploreState,
    Industry,
    Job,
)
from app.models.onboarding import CareerInterviewSession
from app.models.resume import CareerProfile, ProfileRevisionLog, Resume
from app.models.target_job import CapabilityGap, MatchResult, TargetJob
from app.models.prepare import InterviewFocus, PrepPlan, PrepTask, ResumeAdvice
from app.models.tracking import Application, Interview
from app.models.offer import (
    Offer,
    SalaryCalc,
    CityCost,
    UserCityCost,
    OfferDimension,
    AiDimensionReference,
    DecisionWeight,
    ScoreResult,
    DecisionAnalysis,
)
from app.models.user import User, UserProfile

__all__ = [
    "User",
    "UserProfile",
    "EducationExp",
    "InternshipExp",
    "ProjectExp",
    "Skill",
    "Interest",
    "WorkPreference",
    "CareerGoal",
    "Resume",
    "CareerProfile",
    "ProfileRevisionLog",
    "CareerInterviewSession",
    "Industry",
    "Job",
    "Direction",
    "DirectionRecommendation",
    "ExploreState",
    "TargetJob",
    "MatchResult",
    "CapabilityGap",
    "PrepPlan",
    "PrepTask",
    "InterviewFocus",
    "ResumeAdvice",
    "Application",
    "Interview",
    "Offer",
    "SalaryCalc",
    "CityCost",
    "UserCityCost",
    "OfferDimension",
    "AiDimensionReference",
    "DecisionWeight",
    "ScoreResult",
    "DecisionAnalysis",
]
