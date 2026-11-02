


import typing as tp
from .. import utils
from .. import types
from .. import configs
import array
import math
import sys
from collections import deque
from time import monotonic

from .audio import portaudio, portaudio_available


SAMPLE_RATE = 24000
CHANNELS = 1










BLOCK_SIZE = 512
_HELPER = portaudio_available() and portaudio.helper_available
LATENCY = 0.05 if sys.platform == "darwin" else 0.02 if _HELPER else 0.15 if sys.platform == "win32" else 0.1
MAX_NO_SIGNAL = 4
HEALTH_CHECK_EVERY = 1
NON_ZERO_CHECK_AMOUNT = round(BLOCK_SIZE / 10)




TARGET_DBFS = -23.0
MIN_GAIN_DB = -6.0
MAX_GAIN_DB = 18.0


LEVEL_SMOOTHING = 0.3

SPEECH_WITHIN_DB = 30.0
SILENT_DBFS = -60.0



PRE_ROLL_BLOCKS = round(0.3 * SAMPLE_RATE / BLOCK_SIZE)

ChunkCallback = tp.Callable[[bytes], None]
NoneCallback = tp.Callable[[], None]
FailedCallback = tp.Callable[[str], None]


class Recorder:

    _stream: "portaudio.RawInputStream | None" = None
    _stream_device: types.InputDevice | None = None
    _ready_for_recording: bool = False
    _health_timer: types.TimerCallback | None = None
    _stream_last_called: float | None = None

    _stream_default_name: str | None = None



    fallback_from: str | None = None


    _session: str | None = None
    _on_chunk: ChunkCallback | None = None
    _on_ready: NoneCallback | None = None
    _on_failed: FailedCallback | None = None

    _gain: float = 1.0
    _levels: list[float] = []

    _preroll: "deque[bytes]" = deque(maxlen=PRE_ROLL_BLOCKS)
    _pending_preroll: list[bytes] | None = None

    @classmethod
    def start(
        cls,
        session_id: str,
        on_failed: FailedCallback,
        on_chunk: ChunkCallback | None = None,
        on_ready: NoneCallback | None = None,
    ):
        if cls._session:
            raise RuntimeError("Recording session already in progress.")
        cls._on_chunk = on_chunk
        cls._on_ready = on_ready
        cls._on_failed = on_failed

        cls._gain = _gain_for(cls._device_key()) if cls._stream else 1.0
        cls._levels = []
        cls._pending_preroll = list(cls._preroll) if cls._stream and cls._ready_for_recording else None
        cls._preroll.clear()

        cls._session = session_id

        if cls._stream:
            if cls._ready_for_recording:
                cls._notify_stream_ready()
        else:
            cls._create_stream()


    @classmethod
    def stop(cls, session_id: str):
        if cls._session == session_id:
            cls._end_session()


    @classmethod
    def shutdown(cls):
        cls._end_session()
        cls._close_stream()



    @classmethod
    def reset(cls) -> bool:
        if cls._session:
            return False
        cls._close_stream()
        cls.fallback_from = None
        return True



    @classmethod
    def can_list_new_devices(cls) -> bool:
        return not cls._session and not (portaudio_available() and portaudio.has_other_streams(cls._stream))


    @classmethod
    def apply_prime_setting(cls):
        if is_prime_mic_enabled():
            if not cls._stream:
                cls._create_stream()
        elif not cls._session:
            cls._close_stream()

    @classmethod
    def is_stream_open(cls) -> bool:
        return cls._stream is not None


    @classmethod
    def stream_device_index(cls) -> int | None:
        return cls._stream.device if cls._stream else None


    @classmethod
    def stream_buffer_frames(cls) -> int | None:
        return cls._stream.device_buffer_frames() if cls._stream else None

    @classmethod
    def _end_session(cls) -> None:
        if not cls._session:
            return
        cls._session = None
        cls._on_chunk = None
        cls._on_ready = None
        cls._on_failed = None
        _learn_level(cls._device_key(), cls._levels)
        cls._levels = []
        cls._pending_preroll = None

        if not is_prime_mic_enabled():
            cls._close_stream()

    @classmethod
    def _create_stream(cls) -> None:
        if cls._stream:
            raise RuntimeError("Cannot create stream when one exists.")


        devices = input_devices()

        if devices is None or len(devices) == 0:
            utils.logger.warning("No input devices found (PortAudio available: %s)", portaudio_available())
            cls._notify_failure("No microphone")
            return


        data = configs.get_config()
        selected = data.get("selected_mic")
        device: types.InputDevice | None = None

        if selected and selected.get("name") != "Default":
            device = get_matching_device(devices, selected)
            if not device:
                utils.logger.warning("Selected microphone %r not found, falling back to default", selected.get("name"))
            elif device["name"] == cls.fallback_from:
                device = None

        try:
            cls._stream = portaudio.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                device=int(device["id"]) if device else None,
                callback=cls._notify_audio_chunk,
                blocksize=BLOCK_SIZE,
                latency=LATENCY,
            )
            cls._ready_for_recording = False
            cls._stream_device = device
            cls._stream_default_name = None if device else default_device_name()

            if cls._session:
                cls._gain = _gain_for(cls._device_key())
            cls._stream.start()
            cls._stream_last_called = monotonic()
            cls._health_timer = utils.register_timer(cls._on_health_monitor, HEALTH_CHECK_EVERY)
            utils.logger.info(
                "Microphone stream opened: %s", device["name"] if device else f"system default ({default_device_name()})"
            )
        except Exception as e:
            utils.logger.exception("Couldn't open microphone stream (device: %s)", device["name"] if device else "system default")
            cls._close_stream()
            if device:

                cls.fallback_from = device["name"]
                utils.logger.warning("Falling back to the default microphone")
                cls._create_stream()
                return
            cls._notify_failure(f"Couldn't open the microphone ({_portaudio_reason(e)})")
            return

    @classmethod
    def _close_stream(cls) -> None:
        if not cls._stream:
            return
        cls._ready_for_recording = False
        cls._stream_device = None
        cls._preroll.clear()
        try:
            cls._stream.stop()
        except Exception:
            pass
        try:
            cls._stream.close()
        except Exception:
            pass
        cls._stream = None
        utils.clear_timer(cls._health_timer)
        cls._health_timer = None

    @classmethod
    def _notify_failure(cls, reason: str):
        utils.logger.warning("Microphone stream failed: %s", reason or "couldn't start")
        if cls._session and cls._on_failed:
            cls._on_failed(reason)
        cls._end_session()
        cls._close_stream()

    @classmethod
    def _notify_audio_chunk(cls, data: bytes, frames: int, time_info: tp.Any, status: int) -> None:
        cls._stream_last_called = monotonic()
        if cls._ready_for_recording:
            if status & portaudio.paInputUnderflow:
                utils.set_timeout(lambda: cls._notify_failure("Microphone disconnected"), 0)
                return
        else:

            if (status & portaudio.paInputUnderflow) or not any(data[-NON_ZERO_CHECK_AMOUNT:]):
                return
            cls._ready_for_recording = True
            utils.set_timeout(cls._notify_stream_ready, 0)

        on_chunk = cls._on_chunk
        if not cls._session or not on_chunk:

            cls._preroll.append(bytes(data))
            return
        pending = cls._pending_preroll
        if pending:
            cls._pending_preroll = None
            for block in pending:
                on_chunk(_apply_gain(block, cls._gain))
        cls._levels.append(_level_dbfs(data))
        on_chunk(_apply_gain(data, cls._gain))


    @classmethod
    def _device_key(cls) -> str | None:
        return cls._stream_device["name"] if cls._stream_device else cls._stream_default_name



    @classmethod
    def silence_message(cls) -> str:
        name = cls._stream_device["name"] if cls._stream_device else cls._stream_default_name
        if not cls._stream_device and sys.platform == "darwin":
            utils.logger.warning(
                "No sound from the default microphone %r. If it's a real microphone, check that Blender may use it "
                "(System Settings → Privacy & Security → Microphone).",
                name,
            )
        return (
            f"No sound from “{name}”. Pick a mic in the Exciton panel."
            if name
            else "No sound from the mic. Pick one in the Exciton panel."
        )

    @classmethod
    def _notify_stream_ready(cls) -> None:
        if cls._on_ready:
            cls._on_ready()

    @classmethod
    def _on_health_monitor(cls) -> float | None:
        if not cls._stream or not cls._stream_last_called:
            return None


        if not cls._stream.active:
            cls._notify_failure("Microphone disconnected")
            return None


        delta = monotonic() - cls._stream_last_called
        if delta > MAX_NO_SIGNAL:
            cls._notify_failure("Microphone disconnected")
            return None
        return HEALTH_CHECK_EVERY






def _level_dbfs(data: bytes) -> float:
    samples = array.array("h", data[: len(data) - len(data) % 2])
    if not samples:
        return -120.0
    power = sum(s * s for s in samples) / len(samples)
    return 10 * math.log10(power / (32768.0 * 32768.0) + 1e-12)


def _apply_gain(data: bytes, gain: float) -> bytes:
    if gain == 1.0:
        return data
    samples = array.array("h", data[: len(data) - len(data) % 2])
    return array.array("h", (max(-32768, min(32767, round(s * gain))) for s in samples)).tobytes()



def _gain_for(device: str | None) -> float:
    level = (configs.get_config().get("mic_levels") or {}).get(device or "")
    if level is None:
        return 1.0
    db = max(MIN_GAIN_DB, min(MAX_GAIN_DB, TARGET_DBFS - level))
    return 10 ** (db / 20)




def _learn_level(device: str | None, levels: list[float]) -> None:
    if not device or not levels:
        return
    loudest = max(levels)
    if loudest < SILENT_DBFS:
        return
    speech = [l for l in levels if l >= loudest - SPEECH_WITHIN_DB]
    level = 10 * math.log10(sum(10 ** (l / 10) for l in speech) / len(speech))
    data = configs.get_config()
    learned = dict(data.get("mic_levels") or {})
    counts = dict(data.get("mic_level_counts") or {})
    previous = learned.get(device)
    count = 0 if previous is None else counts.get(device, 1)
    weight = max(LEVEL_SMOOTHING, 1 / (count + 1))
    learned[device] = level if previous is None else previous + weight * (level - previous)
    counts[device] = count + 1
    data["mic_levels"] = learned
    data["mic_level_counts"] = counts
    try:
        configs.persist()
    except Exception:

        pass



def default_device_name() -> str | None:
    if not portaudio_available():
        return None
    try:
        index = portaudio.get_default_input_device()
        return portaudio.get_device_info(index)["name"] if index >= 0 else None
    except Exception:
        return None



def _portaudio_reason(e: Exception) -> str:
    text = str(e)
    return text.removeprefix("PortAudio error: ") or type(e).__name__




def get_matching_device(devices: list[types.InputDevice], shape: types.InputDevice) -> types.InputDevice | None:
    exact = next((d for d in devices if d["id"] == shape["id"] and d["name"] == shape["name"]), None)
    return exact or find_device_by_name(devices, shape["name"])


def find_device_by_name(devices: list[types.InputDevice], name: str) -> types.InputDevice | None:
    return next((d for d in devices if d["name"] == name), None)



def input_devices() -> list[types.InputDevice] | None:
    if not portaudio_available():
        return None

    if Recorder._stream is None:
        portaudio.terminate()
        portaudio.initialize()
    devices = portaudio.get_input_devices()
    return [{"id": d["index"], "name": d["name"]} for d in devices]


def is_prime_mic_enabled() -> bool:
    data = configs.get_config()
    return data.get("prime_mic") or False
