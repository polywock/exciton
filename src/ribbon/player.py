


import array
import sys
import threading
import typing as tp
from time import monotonic

from .. import configs
from .. import utils
from . import audio
from . import recorder

if tp.TYPE_CHECKING:
    from . import portaudio

SAMPLE_RATE = 24000

FALLBACK_RATE = 48000
BYTES_PER_SECOND = SAMPLE_RATE * 2


PREBUFFER_SECONDS = 0.25

FLUSH_AFTER_SECONDS = 0.15


OUTPUT_LATENCY = 0.2






BUFFERED_LATENCY = {"darwin": 0.02, "win32": 0.1}.get(sys.platform, 0.05)





SHARED_DEVICE_FALLBACK_FRAMES = 2 * recorder.BLOCK_SIZE






Overflow: tp.TypeAlias = tp.Literal["CATCH_UP", "KEEP"]
LIMIT_SECONDS: dict[Overflow, float] = {"CATCH_UP": 20, "KEEP": 15 * 60}


class Player:
    def __init__(self, overflow: Overflow):
        self._overflow = overflow
        self._limit = int(LIMIT_SECONDS[overflow] * BYTES_PER_SECOND)
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._stream: "portaudio.RawOutputStream | None" = None


        self._volume = _reply_volume()

        self._open_failure: str | None = None

        self._closed = False
        self._upsample = False

        self._buffered = False

        self._playing = False

        self._played_by = 0.0


        self.handed_off_at: float | None = None
        self._last_arrival = 0.0


        self._starved = 0
        self._longest_wait = 0.0
        self._received = 0
        self._overflowed = 0


    def ensure_open(self) -> str | None:
        if self._stream or self._closed or self._open_failure:
            return self._open_failure
        if not audio.portaudio_available():
            self._open_failure = "No audio output"
            return self._open_failure
        pa = audio.portaudio
        assert pa is not None
        shared = sys.platform == "darwin" and recorder.Recorder.stream_device_index() == pa.get_default_output_device()
        shared_frames = (recorder.Recorder.stream_buffer_frames() or SHARED_DEVICE_FALLBACK_FRAMES) if shared else 0
        self._buffered = pa.helper_available
        for rate in (SAMPLE_RATE, FALLBACK_RATE):
            stream = None

            self._upsample = rate == FALLBACK_RATE

            latency = shared_frames / rate if shared else BUFFERED_LATENCY if self._buffered else OUTPUT_LATENCY
            try:
                stream = pa.RawOutputStream(
                    samplerate=rate, channels=1, callback=self._next, latency=latency, buffered=self._buffered
                )
                stream.start()
            except Exception as e:
                utils.logger.warning("Couldn't open the speakers at %s Hz: %s", rate, e)
                _close_quietly(stream)
                continue
            self._stream = stream
            utils.logger.info(
                "Speaker stream opened at %s Hz%s", rate, f" (the microphone's device: {shared_frames} frames)" if shared else ""
            )
            return None
        self._open_failure = "Couldn't play audio"
        return self._open_failure

    def is_open(self) -> bool:
        return self._stream is not None


    def play(self, pcm: bytes) -> bool:
        now = monotonic()
        with self._lock:
            if self._closed:
                return False
            if self._last_arrival:
                self._longest_wait = max(self._longest_wait, now - self._last_arrival)
            self._last_arrival = now
            self._received += len(pcm)
            excess = len(self._buffer) + len(pcm) - self._limit
            if excess <= 0:
                self._buffer.extend(pcm)
            elif self._overflow == "CATCH_UP":
                self._buffer.extend(pcm)
                del self._buffer[: excess + excess % 2]
                self._overflowed += excess
            else:
                self._overflowed += len(pcm)
                return False
            return True


    def close_when_played(self):
        def check():
            if not self._stream:
                return None
            with self._lock:
                left = len(self._buffer)


            if left or self._stream.queued_seconds:
                return 0.1

            utils.set_timeout(self.close, self._stream.output_latency + 0.1)
            return None

        utils.register_timer(check, 0.1)


    def close(self):
        with self._lock:
            self._closed = True
            self._buffer.clear()
        stream, self._stream = self._stream, None
        if not stream:
            return
        if self._received:
            utils.logger.info(
                "Speaker stream closed: %.1fs received, ran out %s times, longest wait between pieces %.0f ms, "
                "%s times late to the device, %.1fs over the limit (%s)",
                self._received / BYTES_PER_SECOND,
                self._starved,
                self._longest_wait * 1000,
                stream.underflows,
                self._overflowed / BYTES_PER_SECOND,
                self._overflow,
            )


        _close_quietly(stream)


    def _next(self, frames: int) -> bytes:
        wanted = (frames // 2 if self._upsample else frames) * 2
        now = monotonic()
        with self._lock:
            if not self._playing:
                enough = len(self._buffer) >= PREBUFFER_SECONDS * BYTES_PER_SECOND
                ended = self._buffer and now - self._last_arrival > FLUSH_AFTER_SECONDS
                if not (enough or ended):
                    return b""
                self._playing = True
                if self.handed_off_at is None:
                    self.handed_off_at = now
            data = bytes(self._buffer[:wanted])
            del self._buffer[: len(data)]
            self._played_by = max(self._played_by, now) + len(data) / BYTES_PER_SECOND


            left = self._played_by - now if self._buffered else len(data) / BYTES_PER_SECOND
            if left < wanted / BYTES_PER_SECOND:
                self._playing = False
                if now - self._last_arrival < FLUSH_AFTER_SECONDS:
                    self._starved += 1
        if self._volume != 1:
            data = _scaled(data, self._volume)
        return _double_samples(data) if self._upsample else data


def _close_quietly(stream: "portaudio.RawOutputStream | None"):
    if not stream:
        return
    try:
        stream.close()
    except Exception:
        utils.logger.info("Couldn't close the speaker stream", exc_info=True)



def _reply_volume() -> float:
    snapshot = configs.get_config().get("_active_snapshot") or {}
    volume = snapshot.get("replyVolume")
    return float(volume) if isinstance(volume, (int, float)) and volume > 0 else 1.0





def _scaled(data: bytes, volume: float) -> bytes:
    import numpy as np

    even = len(data) - len(data) % 2
    samples = np.frombuffer(data, dtype=np.int16, count=even // 2).astype(np.float32) * volume
    return np.clip(samples, -32768, 32767).astype(np.int16).tobytes() + data[even:]



def _double_samples(data: bytes) -> bytes:
    samples = array.array("h", data[: len(data) - len(data) % 2])
    out = array.array("h", bytes(len(samples) * 4))
    out[0::2] = samples
    out[1::2] = samples
    return out.tobytes()
