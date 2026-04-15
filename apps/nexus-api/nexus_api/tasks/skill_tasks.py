"""
Skill and Memory Celery tasks — registered with Celery Beat for autonomous operation.
"""
from __future__ import annotations

import asyncio
import logging

from ..celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, name="tasks.refine_skills")
def refine_skills_task(self, force: bool = False) -> dict:
    """
    Daily beat task: iterate every skill in the registry, health-check, and
    invoke the LLM refiner for any that are broken or stale.
    """
    logger.info("SkillRefiner beat task starting (force=%s).", force)
    try:
        from autoswarm_skills.refiner import SkillRefiner
        refiner = SkillRefiner()
        results = refiner.refine_all()
        logger.info("SkillRefiner complete: %s", results)
        return results
    except Exception as exc:
        logger.error("SkillRefiner task failed: %s", exc)
        raise self.retry(exc=exc, countdown=3600) from exc


@celery_app.task(bind=True, max_retries=2, name="tasks.compact_memory")
def compact_memory_task(self, retention_days: int = 30) -> dict:
    """
    Weekly beat task: summarise old FTS5 transcript rows via the LLM and
    replace them with compressed summary entries.
    """
    logger.info("MemoryCompactor beat task starting (retention_days=%d).", retention_days)
    try:
        from nexus_api.tasks.memory_tasks import compact_memory
        result = asyncio.run(compact_memory(retention_days=retention_days))
        logger.info("MemoryCompactor complete: %s", result)
        return result
    except Exception as exc:
        logger.error("MemoryCompactor task failed: %s", exc)
        raise self.retry(exc=exc, countdown=3600) from exc
