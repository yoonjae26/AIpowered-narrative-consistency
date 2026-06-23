from __future__ import annotations

import logging
from time import sleep

from backend.core.config import get_settings
from backend.narrative.analysis_cache import SceneAnalysisCache
from backend.narrative.analysis_enrichment import SceneAnalysisEnrichmentService
from backend.narrative.analysis_queue import SceneAnalysisQueue


logger = logging.getLogger(__name__)


def _policy_signature() -> str:
    settings = get_settings()
    return "|".join([
        settings.analysis_ruleset_version,
        settings.llm_provider,
        settings.llm_model,
        settings.llm_base_url or "",
    ])


def run_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    cache = SceneAnalysisCache(
        ttl_seconds=settings.analysis_cache_ttl_seconds,
        policy_signature=_policy_signature(),
    )
    queue = SceneAnalysisQueue()
    service = SceneAnalysisEnrichmentService(cache)

    logger.info("scene analysis worker started")
    while True:
        claimed = queue.claim_next()
        if claimed is None:
            sleep(settings.analysis_worker_poll_seconds)
            continue

        processing_path, job_payload = claimed
        try:
            service.enrich_from_job(job_payload)
            queue.complete(processing_path)
        except Exception as exc:
            logger.exception("scene analysis enrichment failed for %s", job_payload.get("scene_hash"))
            queue.fail(processing_path, str(exc))


if __name__ == "__main__":
    run_worker()