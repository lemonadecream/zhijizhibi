"""Aggregate API router (versioned under /api)."""
from fastapi import APIRouter

from app.api import auth, config, experience, explore, health, onboarding, offer, prepare, profile, resume, target_job, tracking

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(config.router)
api_router.include_router(auth.router)
api_router.include_router(resume.router)
api_router.include_router(profile.router)
api_router.include_router(experience.router)
api_router.include_router(onboarding.router)
api_router.include_router(explore.router)
api_router.include_router(target_job.router)
api_router.include_router(prepare.router)
api_router.include_router(tracking.router)
api_router.include_router(offer.router)
