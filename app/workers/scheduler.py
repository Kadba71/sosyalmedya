import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.bootstrap import bootstrap_single_user
from app.services.orchestrator import OrchestratorService
from app.workers.cleanup import run_cleanup


logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._scheduler = BackgroundScheduler(timezone=self.settings.default_timezone)
        self._configured = False

    def start(self) -> None:
        if self._configured:
            if not self._scheduler.running:
                self._scheduler.start()
            return

        self._scheduler.add_job(self._run_daily_scan, CronTrigger(hour=9, minute=0), id="daily_scan", replace_existing=True)
        self._scheduler.add_job(run_cleanup, CronTrigger(minute="*/30"), id="cleanup", replace_existing=True)
        self._scheduler.start()
        self._configured = True

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _run_daily_scan(self) -> None:
        session = SessionLocal()
        try:
            _, project = bootstrap_single_user(session, self.settings)
            OrchestratorService(session, self.settings).daily_scan(project)
        except Exception:
            logger.exception("Daily scan job failed.")
        finally:
            session.close()


scheduler_service = SchedulerService()