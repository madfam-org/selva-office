import logging

from ..celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def run_acp_workflow_task(self, target_url: str):
    """
    Celery task to orchestrate the ACP cycle.
    Executes the LangGraph Phase I Analyst workflow.
    """
    logger.info(f"Executing background ACP dirty analyst task for {target_url}")
    try:
        from selva_workflows.acp_analyst import ACPAnalystNode

        # In a complete implementation, this triggers the compilation and execution of the graph.
        # Since Phase I returns a dict right now:
        node = ACPAnalystNode(target_url=target_url)
        result = node.run()
        logger.info(f"Phase I Analyst complete. PRD length: {len(result.get('prd', ''))}")
        return result
    except Exception as exc:
        logger.error(f"Error in ACP Analyst workflow for {target_url}: {exc}")
        raise self.retry(exc=exc, countdown=60) from exc
