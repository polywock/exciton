import queue
import typing as tp
from time import monotonic

from .. import types
from .. import utils
from .. import registry as rg
from ..api import latency
from .summons import pointer
from .summons import screenshot
from .summons import wait_for_user
from .summons import script
from .summons import command_script
from .summons import operator as operator_summon
from ..commands import availability
from ..commands import context as command_context_module
from . import audio
from . import recorder
from . import server_errors
from . import td
from . import connection
from .display import Display
from .player import Player


MAX_COMMAND_SECONDS = 15

TAP_SECONDS = 0.5



def _ms(a: float, b: float) -> int:
    return round((b - a) * 1000)


_QUEUE_DONE = object()



_server_flags: dict | None = None


def _keep_flags(flags: dict | None):
    global _server_flags
    _server_flags = flags


class RibbonJob:
    def __init__(
        self,
        job_id: str,
        action: types.ChatOrCommand,
        on_done: tp.Callable[[str], None],
        command_context: command_context_module.CommandContext | None = None,
        resume_conversation_id: str | None = None,
        stopped_answer: bool = False,
    ):
        self.id = job_id


        self._stopped_answer = stopped_answer
        self.action = action

        self._command_context = command_context

        self._availability = availability.AvailabilityCheck(command_context) if command_context and action == "COMMAND" else None
        self.state: td.JobState = "recording"
        self.resolved_at: float | None = None
        self.recording_started = False
        self.error_reason: str | None = None

        self.error_kind: tp.Literal["error", "notice"] = "error"
        self._scripts = script.ScriptRunner(self.is_active)
        self._conversation_id: str | None = None
        self._conversation_resumed = False
        self._started_at = monotonic()

        self._on_done = on_done
        self._protocol_state: td.ProtocolState = "1_STARTING"
        self._prelim: td.FromClientMessage | None = None
        self._queue: queue.Queue[bytes | object] = queue.Queue()



        self._resume_handoff_cb: tp.Callable[[], None] | None = None

        self._server_ended = False
        self._resume_conversation_id = resume_conversation_id
        self._resume_probe_received = False
        self._resume_handoff_ready = False




        self._timing: dict[str, float] = {}

        self._watching_playback = False

        self.display = Display()

        self._player = Player("KEEP")

        utils.logger.info("Job %s started: %s (resuming conversation: %s)", self.id, action, self._resume_conversation_id)
        self._connection = connection.connect(
            f"Job {self.id}",
            is_active=self.is_active,
            on_open=self._on_open,
            on_message=self._on_message,
            on_close=self._on_close,
            on_audio=self._on_audio,
        )
        utils.set_timeout(self._set_prelim, 0)
        utils.set_timeout(self._start_recording, 0)
        if self.action == "COMMAND":

            utils.set_timeout(self.seal, MAX_COMMAND_SECONDS)


    def _resolve(self, new_state: tp.Literal["done", "failed"]):
        if not self.is_active():
            return
        self.state = new_state
        self.resolved_at = monotonic()
        if new_state == "done":

            self.display.final = True
        utils.logger.info(
            "Job %s %s after %.1fs (protocol: %s, conversation: %s, recording started: %s, error: %s)",
            self.id,
            new_state,
            self.resolved_at - self._started_at,
            self._protocol_state,
            self._conversation_id,
            self.recording_started,
            self.error_reason,
        )
        self._queue.put(_QUEUE_DONE)
        recorder.Recorder.stop(self.id)

        if new_state == "done":
            self._player.close_when_played()
        else:
            self._player.close()
        if self.action == "COMMAND" and self._server_ended:
            self._connection.release()
        else:
            self._connection.close()
        self._on_done(self.id)
        if self._resume_handoff_cb:
            self._resume_handoff_cb()

    def seal(self):

        released = monotonic()
        recorder.Recorder.stop(self.id)
        if self.state != "recording":
            return
        self._timing["released"] = released
        held = monotonic() - self._started_at
        tap = held < TAP_SECONDS
        utils.logger.info("Job %s: shortcut held %.2fs (stopped an answer: %s)", self.id, held, self._stopped_answer)


        if tap and self._stopped_answer and self.is_active():
            utils.logger.info("Job %s: a tap that stopped an answer, so nothing is sent", self.id)
            self.cancel()
            return
        if not self.recording_started and self.is_active():


            if tap:
                self.error_reason = "Hold the shortcut while you speak."
                self.error_kind = "notice"
            else:
                self.error_reason = recorder.Recorder.silence_message()
                utils.logger.warning("Job %s: no sound from the microphone before release", self.id)
            self._resolve("failed")
            return
        self.state = "sealed"
        self._queue.put(_QUEUE_DONE)

    def cancel(self):
        self._player.close()
        self._resolve("failed")




    def stop(self, cancel_only: bool = False) -> str | None:

        self._player.close()
        if not self.is_active():
            return None
        if self._conversation_id and not cancel_only:
            self._send_data({"type": "INTERRUPT"})
            return self._conversation_id
        self._send_data({"type": "CANCEL"})
        return None


    def interrupt_or_cancel(self, cancel_only: bool) -> str | None:
        self.display.hidden = True
        return self.stop(cancel_only)


    def hand_over_to(self, job: "RibbonJob"):
        self._resume_handoff_cb = job._on_resume_handoff

    def _on_resume_handoff(self):
        if not self.is_active():
            return
        self._resume_handoff_ready = True
        self._try_send_resume_proceed()

    def _try_send_resume_proceed(self):
        if self._resume_conversation_id and self._resume_probe_received and self._resume_handoff_ready:
            self._send_data({"type": "RESUME_PROCEED"})
            self._resume_conversation_id = None

    def is_active(self) -> bool:
        return self.state not in ("done", "failed")


    def recording_label(self, now: float) -> str:
        return "Listening"


    def is_playing(self) -> bool:
        return self._player.is_open()


    def _on_open(self):
        if self._protocol_state == "1_STARTING":
            self._protocol_state = "2_OPEN"

    def _on_close(self):
        self._protocol_state = "CLOSED"
        self._on_message({"type": "ERROR"})


    def _on_audio(self, pcm: bytes):
        self._timing.setdefault("first_audio", monotonic())
        if self._player.play(pcm) and not self._player.is_open():
            utils.set_timeout(self._open_player, 0)

    def _on_message(self, msg: td.FromServerMessage):
        if not self.is_active():
            return


        if msg.get("type") in ("OK", "ERROR") and "received_at" in msg:
            self._server_ended = True
        match msg.get("type"):
            case "OK":
                self._resolve("done")
            case "ERROR":
                error = server_errors.handle(msg, f"Job {self.id}", self._protocol_state)

                if error.reason is None:
                    self.error_reason = None
                elif not self.error_reason:
                    self.error_reason, self.error_kind = error
                self._resolve("failed")
            case "SUMMON":
                self._handle_summon(msg)
            case "FLAGS":
                _keep_flags(msg.get("flags"))
            case "SEND_PRELIM":
                if self._protocol_state != "2_OPEN":
                    utils.logger.warning("Job %s got SEND_PRELIM in %s", self.id, self._protocol_state)
                    return self._on_message({"type": "ERROR"})
                self._protocol_state = "3_READY_PRELIM"
                utils.set_timeout(self._send_prelim_if_ready, 0)
            case "SEND_AUDIO":
                if self._protocol_state != "4_SENT_PRELIM":
                    utils.logger.warning("Job %s got SEND_AUDIO in %s", self.id, self._protocol_state)
                    return self._on_message({"type": "ERROR"})
                self._protocol_state = "5_READY_AUDIO"
                self._timing["ready"] = monotonic()
                self._connection.stream_audio(self._queue, _QUEUE_DONE, on_end=self._audio_ended)
            case "ID_ESTABLISHED":
                self._conversation_id = msg.get("conversation_id")
                self._conversation_resumed = bool(msg.get("conversation_resumed"))
                utils.logger.info(
                    "Job %s conversation %s (resumed: %s)", self.id, self._conversation_id, self._conversation_resumed
                )


                if msg.get("spoken"):
                    self._open_player()
                    if not self._watching_playback:
                        self._watching_playback = True
                        utils.register_timer(self._report_spoken_latency, 0.1)
            case "RESUME_PROBE":
                self._resume_probe_received = True
                self._try_send_resume_proceed()
            case "UPDATE":
                update = msg.get("update")
                if update:
                    self.display.tool = update.get("tool")
                    self.display.add(update.get("text"), final=bool(update.get("final")))


                    if self.display.final and not self._resume_handoff_cb:
                        self._resolve("done")



    def _handle_summon(self, msg: td.FromServerMessage):
        summon_id = msg.get("summon_id")
        if not summon_id:
            utils.logger.warning("Job %s got a summon without ID", self.id)
            return self._on_message({"type": "ERROR"})

        summon_type = msg.get("summon_type")
        utils.logger.debug("Job %s summon %s: %s", self.id, summon_id, summon_type)
        if summon_type == "RUN_SCRIPT":

            if self.action != "CHAT":
                utils.logger.warning("Job %s (%s) got a script: not run", self.id, self.action)
                return self._on_summon_reply(summon_id, {"status": "ERROR", "error": "Scripts only run in chats", "logs": []})
            self._scripts.run(
                msg,
                on_resolve=lambda reply: self._on_summon_reply(summon_id, reply),
                on_waiting=lambda: self._send_data({"type": "SUMMON_WAITING", "summon_id": summon_id}),
            )
        elif summon_type == "SCREENSHOT":
            if self.action != "CHAT":
                utils.logger.warning("Job %s (%s) got a screenshot request: not taken", self.id, self.action)
                return self._on_summon_reply(summon_id, {"status": "ERROR", "error": "Screenshots only in chats", "logs": []})
            shot = screenshot.SummonScreenshot.start(msg, on_resolve=lambda reply: self._on_summon_reply(summon_id, reply))
            if shot:
                shot.run(self.is_active, on_waiting=lambda: self._send_data({"type": "SUMMON_WAITING", "summon_id": summon_id}))
            else:
                self._on_summon_reply(summon_id, {"status": "ERROR", "error": "Invalid screenshot request", "logs": []})
        elif summon_type == "POINT":
            if self.action != "CHAT":
                return self._on_summon_reply(summon_id, {"status": "ERROR", "error": "Pointing only in chats", "logs": []})
            point = pointer.SummonPoint.start(msg, on_resolve=lambda reply: self._on_summon_reply(summon_id, reply))
            if point:
                point.run()
            else:
                self._on_summon_reply(summon_id, {"status": "ERROR", "error": "Invalid point request", "logs": []})
        elif summon_type == "WAIT_FOR_USER":
            if self.action != "CHAT":
                return self._on_summon_reply(summon_id, {"status": "ERROR", "error": "Waiting only in chats", "logs": []})
            waiter = wait_for_user.SummonWaitForUser.start(msg, on_resolve=lambda reply: self._on_summon_reply(summon_id, reply))
            if waiter:
                waiter.run(self.is_active)
            else:
                self._on_summon_reply(summon_id, {"status": "ERROR", "error": "Invalid wait request", "logs": []})
        elif summon_type == "RUN_COMMAND_SCRIPT":
            if self.action != "COMMAND":
                utils.logger.warning("Job %s (%s) got a script command: not run", self.id, self.action)
                return self._on_summon_reply(
                    summon_id, {"status": "ERROR", "error": "Script commands only run as commands", "logs": []}
                )
            self._timing["command_received"] = msg.get("received_at") or monotonic()
            self._timing["command_handled"] = monotonic()
            summon = command_script.SummonCommandScript.start(
                msg,
                self._command_context,
                on_resolve=lambda reply: self._on_operator_reply(summon_id, reply),
                on_ran=self._log_command_timing,
            )
            if summon:
                summon.run(self.is_active, on_waiting=lambda: self._send_data({"type": "SUMMON_WAITING", "summon_id": summon_id}))
            else:
                self._on_summon_reply(summon_id, {"status": "ERROR", "error": "Invalid command request", "logs": []})
        elif summon_type == "RUN_OPERATOR":
            self._timing["command_received"] = msg.get("received_at") or monotonic()
            self._timing["command_handled"] = monotonic()
            summon = operator_summon.SummonOperator.start(
                msg,
                self._command_context,
                on_resolve=lambda reply: self._on_operator_reply(summon_id, reply),
                on_ran=self._log_command_timing,
            )
            if summon:
                summon.run(self.is_active, on_waiting=lambda: self._send_data({"type": "SUMMON_WAITING", "summon_id": summon_id}))
            else:
                self._on_summon_reply(summon_id, {"status": "ERROR", "error": "Invalid command request", "logs": []})

    def _on_operator_reply(self, id: str, reply: td.SummonResponse):
        if reply.get("status") == "OK" and reply.get("result"):


            self.display.add(reply.get("result"), final=True, state=reply.get("state"))
            rg.Overlay.refresh()
        self._on_summon_reply(id, reply)



    def _log_command_timing(self, started: float, finished: float):
        t = self._timing
        released, received = t.get("released"), t.get("command_received")
        if released is None or received is None:
            return
        ms = lambda a, b: f"{(b - a) * 1000:.0f} ms"
        ready = t.get("ready")
        if ready is None or ready > released:
            taken = f"audio taken {ms(released, ready)} after release" if ready else "audio never taken"
        else:
            taken = f"audio taken {ms(ready, released)} before release"
        if ready is not None:
            taken += f", {ms(self._started_at, ready)} from press"
        rtt = self._connection.rtt_ms()
        utils.logger.info(
            "Job %s command timing: release to end sent %s, to command received %s (server and network), to handled %s, "
            "to operator started %s, operator ran %s; %s from release to done; %s; on %s; socket RTT %s",
            self.id,
            ms(released, t.get("end_sent", released)),
            ms(t.get("end_sent", released), received),
            ms(received, t.get("command_handled", received)),
            ms(t.get("command_handled", received), started),
            ms(started, finished),
            ms(released, finished),
            taken,
            self._connection.how,
            f"{rtt} ms" if rtt is not None else "unknown",
        )
        timings = {"releaseToOperatorStartMs": _ms(released, started), "operatorRunMs": _ms(started, finished)}
        if rtt is not None:
            timings["socketRttMs"] = rtt
        end_sent, handled = t.get("end_sent"), t.get("command_handled")
        if end_sent is not None:
            timings["releaseToEndSentMs"] = _ms(released, end_sent)
            timings["endSentToCommandMs"] = _ms(end_sent, received)
        if handled is not None:
            timings["commandToHandledMs"] = _ms(received, handled)
            timings["handledToOperatorStartMs"] = _ms(handled, started)
        if ready is not None:
            timings["audioTakenAfterReleaseMs"] = _ms(released, ready)
            timings["pressToAudioTakenMs"] = _ms(self._started_at, ready)
        latency.report(self.id, "COMMAND", timings, connection=self._connection.kind)





    def _report_spoken_latency(self) -> float | None:
        handed_off = self._player.handed_off_at

        if handed_off is None and (self.is_active() or self._player.is_open()):
            return 0.1
        released, first_audio = self._timing.get("released"), self._timing.get("first_audio")
        timings: dict[str, int] = {}
        if released is not None and first_audio is not None:
            timings["releaseToFirstAudioMs"] = _ms(released, first_audio)
        if released is not None and handed_off is not None:
            timings["releaseToPlaybackHandoffMs"] = _ms(released, handed_off)
        if timings:
            latency.report(self.id, "CHAT", timings)
        return None

    def _on_summon_reply(self, id: str, response: td.SummonResponse):
        self._send_data({"type": "SUMMON_RESULT", "summon_id": id, "summon_response": response})

    def _start_recording(self):

        if self.state != "recording":
            return
        recorder.Recorder.start(
            self.id,
            on_failed=self._recording_failed,
            on_chunk=self._recording_chunk,
            on_ready=self._recording_ready,
        )


    def _open_player(self):
        if self.display.hidden or not self.is_active():
            return
        failed = self._player.ensure_open()
        if failed:

            utils.logger.warning("Job %s can't play its answer: %s", self.id, failed)
            self.error_reason = failed
            self._resolve("failed")

    def _recording_failed(self, reason: str = ""):
        self._on_message({"type": "ERROR", "error": reason or "Recording failed"})

    def _recording_chunk(self, data: bytes):
        if self.state == "recording":
            self._queue.put(data)

    def _recording_ready(self):
        self.recording_started = True

    def _set_prelim(self):
        self._prelim = {
            "type": "SENT_PRELIM",
            "prelim_payload": {
                "action": self.action,

                "jobId": self.id,
                "audioFormat": {"channels": 1, "sampleRate": 24000, "sampleWidth": 2},
                "conversationId": self._resume_conversation_id,
            },
        }
        if self.action == "CHAT" and audio.portaudio_available():

            self._prelim["prelim_payload"]["playsAudio"] = True
        if self._command_context:
            self._prelim["prelim_payload"].update(command_context_module.prelim_fields(self._command_context))
        if self.action == "COMMAND" and _server_flags:
            self._prelim["prelim_payload"]["flags"] = _server_flags
        self._send_prelim_if_ready()

    def _send_prelim_if_ready(self):
        if not self.is_active():
            return
        if self._prelim and self._protocol_state == "3_READY_PRELIM":
            if self._availability:
                self._prelim["prelim_payload"]["unavailableCommands"] = self._availability.finish()
            self._connection.send_json(self._prelim)
            self._protocol_state = "4_SENT_PRELIM"


    def _audio_ended(self):
        self._timing["end_sent"] = monotonic()
        self._protocol_state = "6_SENT_AUDIO"

    def _send_data(self, data: td.FromClientMessage):
        self._connection.send_json(data)
