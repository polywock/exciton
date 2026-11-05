









import math
import queue
import typing as tp
from time import monotonic

from .. import utils
from ..commands import context as command_context_module
from .summons import pointer
from .summons import screenshot
from .summons import script
from . import recorder
from . import server_errors
from . import td
from . import connection
from .display import Display
from .player import Player


MAX_SECONDS = 180

COUNTDOWN_SECONDS = 60

QUICK_END_SECONDS = 2.0

_QUEUE_DONE = object()


class LiveJob:
    action: tp.Literal["CHAT"] = "CHAT"

    def __init__(
        self,
        job_id: str,
        on_done: tp.Callable[[str], None],
        command_context: command_context_module.CommandContext | None = None,
    ):
        self.id = job_id

        self._command_context = command_context

        self.state: td.JobState = "recording"
        self.resolved_at: float | None = None
        self.error_reason: str | None = None
        self.error_kind: tp.Literal["error", "notice"] = "error"
        self._mic_ready = False
        self._scripts = script.ScriptRunner(self.is_active)
        self._started_at = monotonic()

        self._on_done = on_done
        self._protocol_state: td.ProtocolState = "1_STARTING"
        self._queue: queue.Queue[bytes | object] = queue.Queue()

        self._player = Player("CATCH_UP")


        self.display = Display()

        utils.logger.info("Live job %s started", self.id)
        self._connection = connection.connect(
            f"Live job {self.id}",
            is_active=self.is_active,
            on_open=self._on_open,
            on_message=self._on_message,
            on_close=self._on_close,
            on_audio=self._on_audio,
        )
        utils.set_timeout(self._start_recording, 0)
        utils.set_timeout(self._reach_limit, MAX_SECONDS)


    @property
    def recording_started(self) -> bool:
        return self._mic_ready and self._protocol_state == "5_READY_AUDIO"


    def recording_label(self, now: float) -> str:
        left = MAX_SECONDS - (now - self._started_at)
        return f"Live chat ({max(0, math.ceil(left))}s)" if left <= COUNTDOWN_SECONDS else "Live chat"

    def is_active(self) -> bool:
        return self.state not in ("done", "failed")


    def is_playing(self) -> bool:
        return self.is_active() and self._player.is_open()


    def _resolve(self, new_state: tp.Literal["done", "failed"]):
        if not self.is_active():
            return
        self.state = new_state
        self.resolved_at = monotonic()
        self.display.tool = None
        self.display.final = True
        utils.logger.info(
            "Live job %s %s after %.1fs (protocol: %s, error: %s)",
            self.id,
            new_state,
            self.resolved_at - self._started_at,
            self._protocol_state,
            self.error_reason,
        )
        self._queue.put(_QUEUE_DONE)
        recorder.Recorder.stop(self.id)
        self._player.close()
        self._connection.close()
        self._on_done(self.id)


    def seal(self):
        recorder.Recorder.stop(self.id)
        self._player.close()
        if self.state != "recording":
            return
        if not self._mic_ready:

            if monotonic() - self._started_at >= QUICK_END_SECONDS:
                self.error_reason = recorder.Recorder.silence_message()
                utils.logger.warning("Live job %s: no sound from the microphone before it ended", self.id)
            self._resolve("failed")
            return
        self.state = "sealed"

        self.display.tool = None
        self.display.final = True
        self._queue.put(_QUEUE_DONE)

    def _reach_limit(self):
        if self.state != "recording":
            return
        self.error_reason = f"Live chat ended ({MAX_SECONDS // 60} minute limit)"
        self.error_kind = "notice"
        self.seal()

    def cancel(self):
        self._resolve("failed")



    def stop(self, cancel_only: bool = False) -> str | None:
        self.seal()
        return None

    def interrupt_or_cancel(self, cancel_only: bool) -> str | None:
        self.display.hidden = True
        return self.stop(cancel_only)


    def _on_open(self):
        if self._protocol_state == "1_STARTING":
            self._protocol_state = "2_OPEN"

    def _on_close(self):
        self._protocol_state = "CLOSED"
        self._on_message({"type": "ERROR"})


    def _on_audio(self, pcm: bytes):
        if self.state == "recording":
            self._player.play(pcm)

    def _on_message(self, msg: td.FromServerMessage):
        if not self.is_active():
            return

        match msg.get("type"):
            case "OK":

                self._resolve("failed" if self.error_reason else "done")
            case "ERROR":
                error = server_errors.handle(msg, f"Live job {self.id}", self._protocol_state)

                if error.reason is None:
                    self.error_reason = None
                elif not self.error_reason:
                    self.error_reason, self.error_kind = error
                self._resolve("failed")
            case "SUMMON":
                self._handle_summon(msg)
            case "SEND_PRELIM":
                if self._protocol_state != "2_OPEN":
                    return self._on_message({"type": "ERROR"})
                self._protocol_state = "3_READY_PRELIM"
                prelim: td.Prelim = {
                    "action": "LIVE_CHAT",
                    "audioFormat": {"channels": 1, "sampleRate": recorder.SAMPLE_RATE, "sampleWidth": 2},
                }
                if self._command_context:
                    prelim.update(command_context_module.prelim_fields(self._command_context))
                self._connection.send_json({"type": "SENT_PRELIM", "prelim_payload": prelim})
                self._protocol_state = "4_SENT_PRELIM"
            case "SEND_AUDIO":
                if self._protocol_state != "4_SENT_PRELIM":
                    return self._on_message({"type": "ERROR"})

                failed = self._player.ensure_open() if self.state == "recording" else None
                if failed:
                    self.error_reason = failed
                    return self._resolve("failed")
                self._protocol_state = "5_READY_AUDIO"
                self._connection.stream_audio(self._queue, _QUEUE_DONE, on_end=self._audio_ended)
            case "UPDATE":
                update = msg.get("update")
                if update and self.state == "recording":
                    self.display.tool = update.get("tool")

    def _handle_summon(self, msg: td.FromServerMessage):
        summon_id = msg.get("summon_id")
        summon_type = msg.get("summon_type")
        if not summon_id or summon_type not in ("RUN_SCRIPT", "SCREENSHOT", "POINT"):
            utils.logger.warning("Live job %s got an unexpected summon: %s", self.id, summon_type)
            return

        def on_resolve(reply: td.SummonResponse):
            self._on_summon_reply(summon_id, reply)

        def on_waiting():
            self._connection.send_json({"type": "SUMMON_WAITING", "summon_id": summon_id})

        if summon_type == "RUN_SCRIPT":
            self._scripts.run(msg, on_resolve=on_resolve, on_waiting=on_waiting)
            return
        if summon_type == "POINT":
            point = pointer.SummonPoint.start(msg, on_resolve=on_resolve)
            if point:
                point.run()
            else:
                on_resolve({"status": "ERROR", "error": "Invalid point request", "logs": []})
            return
        shot = screenshot.SummonScreenshot.start(msg, on_resolve=on_resolve)
        if shot:
            shot.run(self.is_active, on_waiting=on_waiting)
        else:
            on_resolve({"status": "ERROR", "error": "Invalid screenshot request", "logs": []})

    def _on_summon_reply(self, id: str, response: td.SummonResponse):
        self._connection.send_json({"type": "SUMMON_RESULT", "summon_id": id, "summon_response": response})

    def _start_recording(self):

        if self.state != "recording":
            return
        recorder.Recorder.start(
            self.id,
            on_failed=lambda reason="": self._on_message({"type": "ERROR", "error": reason or "Recording failed"}),
            on_chunk=self._recording_chunk,
            on_ready=self._recording_ready,
        )

    def _recording_chunk(self, data: bytes):
        if self.state == "recording":
            self._queue.put(data)

    def _recording_ready(self):
        self._mic_ready = True


    def _audio_ended(self):
        self._protocol_state = "6_SENT_AUDIO"
