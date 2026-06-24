"""排程引擎 — 基於 APScheduler 的任務排程器"""
from datetime import datetime
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from utils.config import load_schedules, save_schedules


class ScheduleJob:
    def __init__(
        self,
        job_id: str,
        account_id: str,
        job_type: str,
        cron_expr: str,
        params: dict = None,
        enabled: bool = True,
    ):
        self.job_id = job_id
        self.account_id = account_id
        self.job_type = job_type
        self.cron_expr = cron_expr
        self.params = params or {}
        self.enabled = enabled
        self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "account_id": self.account_id,
            "job_type": self.job_type,
            "cron_expr": self.cron_expr,
            "params": self.params,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "ScheduleJob":
        job = ScheduleJob(
            job_id=data["job_id"],
            account_id=data["account_id"],
            job_type=data["job_type"],
            cron_expr=data["cron_expr"],
            params=data.get("params", {}),
            enabled=data.get("enabled", True),
        )
        job.created_at = data.get("created_at", datetime.now().isoformat())
        return job


class Scheduler:
    """排程管理器"""

    def __init__(self):
        self._scheduler = BackgroundScheduler()
        self._jobs: dict[str, ScheduleJob] = {}
        self._callbacks: dict[str, Callable] = {}

    def register_callback(self, job_type: str, callback: Callable):
        """註冊任務類型對應的執行函數"""
        self._callbacks[job_type] = callback

    def add_job(self, job: ScheduleJob) -> bool:
        """新增排程任務"""
        if job.job_id in self._jobs:
            return False

        parts = job.cron_expr.strip().split()
        if len(parts) != 5:
            return False

        try:
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )

            self._scheduler.add_job(
                self._execute_job,
                trigger=trigger,
                args=[job.job_id],
                id=job.job_id,
                misfire_grace_time=300,
            )

            self._jobs[job.job_id] = job
            self._persist()
            return True
        except Exception as e:
            # 不能直接 print，寫到操作日誌方便 UI 看到
            try:
                from utils.logger import log
                log("SCHEDULER", "system", f"add_job 失敗: {job.job_type}", "❌", detail=str(e)[:150])
            except Exception:
                pass
            return False

    def remove_job(self, job_id: str) -> bool:
        """移除排程任務"""
        if job_id in self._jobs:
            self._scheduler.remove_job(job_id)
            del self._jobs[job_id]
            self._persist()
            return True
        return False

    def pause_job(self, job_id: str) -> bool:
        """暫停排程"""
        if job_id in self._jobs:
            self._scheduler.pause_job(job_id)
            self._jobs[job_id].enabled = False
            self._persist()
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        """恢復排程"""
        if job_id in self._jobs:
            self._scheduler.resume_job(job_id)
            self._jobs[job_id].enabled = True
            self._persist()
            return True
        return False

    def get_jobs(self) -> list[ScheduleJob]:
        return list(self._jobs.values())

    def _execute_job(self, job_id: str):
        """執行任務"""
        job = self._jobs.get(job_id)
        if not job or not job.enabled:
            return
        callback = self._callbacks.get(job.job_type)
        if callback:
            callback(job.account_id, job.params)

    def start(self):
        """啟動排程器"""
        self._scheduler.start()

    def stop(self):
        """停止排程器"""
        self._scheduler.shutdown(wait=False)

    # ── 整體暫停/恢復（供系統匣使用） ─────────────────────────────

    def pause(self):
        """暫停所有排程（不移除 job）"""
        try:
            # APScheduler 3.x 支援 pause/resume
            self._scheduler.pause()
        except Exception:
            # fallback：逐一 pause job
            for jid in list(self._jobs.keys()):
                try:
                    self._scheduler.pause_job(jid)
                except Exception:
                    pass

    def resume(self):
        """恢復所有排程"""
        try:
            self._scheduler.resume()
        except Exception:
            for jid in list(self._jobs.keys()):
                try:
                    self._scheduler.resume_job(jid)
                except Exception:
                    pass

    def load_persisted(self):
        """從磁碟載入已儲存的排程"""
        raw = load_schedules()
        for item in raw:
            try:
                job = ScheduleJob.from_dict(item)
                if job.enabled:
                    self.add_job(job)
                else:
                    self._jobs[job.job_id] = job
            except Exception:
                continue

    def _persist(self):
        save_schedules([j.to_dict() for j in self._jobs.values()])
