import typing as tp
from time import monotonic

from .. import utils
from .. import configs


from . import audio
from . import recorder
from .job import RibbonJob
from .live_job import LiveJob
from .display import Display
from .. import types
from ..commands.context import CommandContext



AnyJob: tp.TypeAlias = RibbonJob | LiveJob


class Ribbon:
    _latest_job: AnyJob | None = None
    _jobs: list[AnyJob] = []


    @classmethod
    def start(cls, action: types.ChatOrCommand, command_context: CommandContext | None = None):
        if not cls._can_start(action):
            return
        cls._make_way_for_recording()




        stopped_answer = action == "CHAT" and any(
            earlier.is_active() or earlier.is_playing() or earlier.display.on_screen() for earlier in cls._jobs
        )


        handing_over: RibbonJob | None = None
        conversation_id: str | None = None
        for earlier in cls._jobs:
            interrupted_id = earlier.interrupt_or_cancel(cancel_only=handing_over is not None)

            if interrupted_id and isinstance(earlier, RibbonJob):
                handing_over, conversation_id = earlier, interrupted_id

        job = RibbonJob(
            utils.random_id(),
            action,
            cls._on_job_done,
            command_context,
            resume_conversation_id=conversation_id,
            stopped_answer=stopped_answer,
        )
        if handing_over:
            handing_over.hand_over_to(job)
        cls._jobs.append(job)
        cls._latest_job = job



    @classmethod
    def toggle_live(cls, command_context: CommandContext | None = None) -> tp.Literal["started", "ended"] | None:
        if cls._end_live():
            return "ended"
        if not cls._can_start("CHAT"):
            return None
        cls._make_way_for_recording()


        for earlier in cls._jobs:
            earlier.interrupt_or_cancel(cancel_only=False)
        live = LiveJob(utils.random_id(), cls._on_job_done, command_context)
        cls._jobs.append(live)
        cls._latest_job = live
        return "started"



    @classmethod
    def live_chat_enabled(cls) -> bool:
        snapshot = configs.get_config().get("_active_snapshot") or {}
        return bool(snapshot.get("liveChat"))

    @classmethod
    def _can_start(cls, action: str) -> bool:
        data = configs.get_config()
        if not data.get("token") or not utils.allows_internet():
            utils.logger.info("Ignoring %s shortcut: signed out or online access is off", action)
            return False
        return True



    @classmethod
    def _make_way_for_recording(cls):
        cls._end_live()
        if cls._latest_job and cls._latest_job.is_active() and cls._latest_job.state == "recording":
            cls.cancel()


    @classmethod
    def _end_live(cls) -> bool:
        ended = False
        for job in cls._jobs:
            if isinstance(job, LiveJob) and job.state == "recording":
                job.seal()
                ended = True
        return ended


    @classmethod
    def stop(cls):
        if not cls._latest_job or not cls._latest_job.is_active() or isinstance(cls._latest_job, LiveJob):
            return
        job = cls._latest_job
        cls._latest_job = None
        job.seal()

    @classmethod
    def cancel(cls):
        if not cls._latest_job or not cls._latest_job.is_active():
            return
        job = cls._latest_job
        cls._latest_job = None
        job.cancel()

    @classmethod
    def cancel_all(cls):
        cls._latest_job = None

        for job in cls._jobs:
            job.cancel()





    @classmethod
    def dismiss(cls):
        for job in cls._jobs:
            if job.state == "recording" or job.display.hidden:
                continue
            job.stop()
            job.display.dismiss()



    @classmethod
    def prune(cls, showing: tp.Callable[[AnyJob], bool]):
        replay = cls.replay_target()
        cls._jobs[:] = [job for job in cls._jobs if job.is_active() or job is replay or showing(job) or job.is_playing()]


    @classmethod
    def has_jobs(cls) -> bool:
        return bool(cls._jobs)


    @classmethod
    def replay_target(cls) -> AnyJob | None:
        for job in reversed(cls._jobs):
            if job.display.texts and not job.display.hidden and job.state in ("sealed", "done"):
                return job
        return None



    @classmethod
    def replay(cls, step: int) -> Display | None:
        job = cls.replay_target()
        if job:
            job.display.replay(step, monotonic())
        return job.display if job else None


    @classmethod
    def move_on(cls) -> Display | None:
        job = cls.replay_target()
        if job:
            job.display.move_on(monotonic())
        return job.display if job else None

    @classmethod
    def _on_job_done(cls, job_id: str):
        if cls._latest_job and cls._latest_job.id == job_id:
            cls._latest_job = None
