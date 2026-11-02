import ctypes
import platform
import sys
import os
import threading
import time
from ctypes import (
    POINTER,
    CFUNCTYPE,
    Structure,
    c_int,
    c_ulong,
    c_double,
    c_char_p,
    c_void_p,
    byref,
)
import typing as tp
import logging


PaError = c_int
PaDeviceIndex = c_int
PaHostApiIndex = c_int
PaTime = c_double
PaSampleFormat = c_ulong
PaStreamFlags = c_ulong
PaStreamCallbackFlags = c_ulong


paInt16 = 0x00000008


paNoFlag = 0


paContinue = 0


paInputUnderflow = 0x00000001
paInputOverflow = 0x00000002
paOutputUnderflow = 0x00000004


paInputOverflowed = -9981


POLL_SECONDS = 0.002

WRITE_FRAMES = 256


RING_SECONDS = 1.0

THREAD_JOIN_SECONDS = 1.0

_BUFFER_FRAME_SIZE = 0x6673697A



SUGGESTED_LATENCY = 0.1


class PaDeviceInfo(Structure):
    _fields_ = [
        ("structVersion", c_int),
        ("name", c_char_p),
        ("hostApi", PaHostApiIndex),
        ("maxInputChannels", c_int),
        ("maxOutputChannels", c_int),
        ("defaultLowInputLatency", PaTime),
        ("defaultLowOutputLatency", PaTime),
        ("defaultHighInputLatency", PaTime),
        ("defaultHighOutputLatency", PaTime),
        ("defaultSampleRate", c_double),
    ]


class PaStreamParameters(Structure):
    _fields_ = [
        ("device", PaDeviceIndex),
        ("channelCount", c_int),
        ("sampleFormat", PaSampleFormat),
        ("suggestedLatency", PaTime),
        ("hostApiSpecificStreamInfo", c_void_p),
    ]


class PaStreamInfo(Structure):
    _fields_ = [
        ("structVersion", c_int),
        ("inputLatency", PaTime),
        ("outputLatency", PaTime),
        ("sampleRate", c_double),
    ]


class PaStreamCallbackTimeInfo(Structure):
    _fields_ = [
        ("inputBufferAdcTime", PaTime),
        ("currentTime", PaTime),
        ("outputBufferDacTime", PaTime),
    ]






PaStreamCallback = CFUNCTYPE(
    c_int,
    c_void_p,
    c_void_p,
    c_ulong,
    POINTER(PaStreamCallbackTimeInfo),
    PaStreamCallbackFlags,
    c_void_p,
)



_LIBS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "libs")



def _load_portaudio():

    libs_dir = _LIBS_DIR

    if sys.platform == "darwin":
        lib_names = [
            os.path.join(libs_dir, "libportaudio.dylib"),
            "libportaudio.dylib",
            "libportaudio.2.dylib",
            "/opt/homebrew/lib/libportaudio.dylib",
            "/usr/local/lib/libportaudio.dylib",
        ]
    elif sys.platform == "win32":


        arch = platform.machine().lower()
        dlls = ["portaudio_arm64.dll", "portaudio_x64.dll"]
        if arch not in ("arm64", "aarch64"):
            dlls.reverse()
        lib_names = [
            *(os.path.join(libs_dir, dll) for dll in dlls),
            os.path.join(libs_dir, "portaudio.dll"),
            "portaudio.dll",
        ]
    elif platform.system() == "Linux":

        lib_names = [
            "libportaudio.so.2",
            "libportaudio.so",
        ]
    else:

        lib_names = []

    for name in lib_names:
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue

    return None


_lib = _load_portaudio()
available = _lib is not None




def _load_helper():
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if sys.platform == "darwin":
        names = ["libexciton_audio.dylib"]
    elif sys.platform == "win32":

        names = ["exciton_audio_arm64.dll", "exciton_audio_x64.dll"]
        if not arm:
            names.reverse()
    elif sys.platform.startswith("linux"):
        names = ["libexciton_audio_aarch64.so" if arm else "libexciton_audio_x86_64.so"]
    else:
        names = []
    for name in names:
        try:
            helper = ctypes.CDLL(os.path.join(_LIBS_DIR, name))
        except OSError:
            continue
        helper.exciton_ring_new.restype = c_void_p
        helper.exciton_ring_new.argtypes = [ctypes.c_size_t, ctypes.c_uint32]
        helper.exciton_ring_free.restype = None
        helper.exciton_ring_free.argtypes = [c_void_p]
        for fn in ("exciton_ring_used", "exciton_ring_free_space"):
            getattr(helper, fn).restype = ctypes.c_size_t
            getattr(helper, fn).argtypes = [c_void_p]
        helper.exciton_ring_overflows.restype = ctypes.c_uint64
        helper.exciton_ring_overflows.argtypes = [c_void_p]
        for fn in ("exciton_ring_write", "exciton_ring_read"):
            getattr(helper, fn).restype = ctypes.c_size_t
            getattr(helper, fn).argtypes = [c_void_p, c_void_p, ctypes.c_size_t]
        return helper
    return None


_helper = _load_helper()
helper_available = _helper is not None

_HELPER_INPUT = PaStreamCallback(ctypes.cast(_helper.exciton_audio_input, c_void_p).value) if _helper else None
_HELPER_OUTPUT = PaStreamCallback(ctypes.cast(_helper.exciton_audio_output, c_void_p).value) if _helper else None


_initialized = False



_open_streams: "set[_Stream]" = set()


if _lib is not None:
    _lib.Pa_Initialize.restype = PaError
    _lib.Pa_Initialize.argtypes = []

    _lib.Pa_Terminate.restype = PaError
    _lib.Pa_Terminate.argtypes = []

    _lib.Pa_GetErrorText.restype = c_char_p
    _lib.Pa_GetErrorText.argtypes = [PaError]

    _lib.Pa_GetDeviceCount.restype = PaDeviceIndex
    _lib.Pa_GetDeviceCount.argtypes = []

    _lib.Pa_GetDeviceInfo.restype = POINTER(PaDeviceInfo)
    _lib.Pa_GetDeviceInfo.argtypes = [PaDeviceIndex]

    _lib.Pa_GetDefaultInputDevice.restype = PaDeviceIndex
    _lib.Pa_GetDefaultInputDevice.argtypes = []

    _lib.Pa_GetDefaultOutputDevice.restype = PaDeviceIndex
    _lib.Pa_GetDefaultOutputDevice.argtypes = []

    _lib.Pa_OpenStream.restype = PaError
    _lib.Pa_OpenStream.argtypes = [
        POINTER(c_void_p),
        POINTER(PaStreamParameters),
        POINTER(PaStreamParameters),
        c_double,
        c_ulong,
        PaStreamFlags,
        PaStreamCallback,
        c_void_p,
    ]

    _lib.Pa_StartStream.restype = PaError
    _lib.Pa_StartStream.argtypes = [c_void_p]

    _lib.Pa_StopStream.restype = PaError
    _lib.Pa_StopStream.argtypes = [c_void_p]

    _lib.Pa_CloseStream.restype = PaError
    _lib.Pa_CloseStream.argtypes = [c_void_p]

    _lib.Pa_IsStreamActive.restype = PaError
    _lib.Pa_IsStreamActive.argtypes = [c_void_p]

    _lib.Pa_ReadStream.restype = PaError
    _lib.Pa_ReadStream.argtypes = [c_void_p, c_void_p, c_ulong]

    _lib.Pa_GetStreamReadAvailable.restype = ctypes.c_long
    _lib.Pa_GetStreamReadAvailable.argtypes = [c_void_p]

    _lib.Pa_GetStreamInfo.restype = POINTER(PaStreamInfo)
    _lib.Pa_GetStreamInfo.argtypes = [c_void_p]

    if sys.platform == "darwin" and hasattr(_lib, "PaMacCore_GetStreamInputDevice"):
        _lib.PaMacCore_GetStreamInputDevice.restype = ctypes.c_uint32
        _lib.PaMacCore_GetStreamInputDevice.argtypes = [c_void_p]
        _lib.PaMacCore_AudioDeviceGetProperty.restype = ctypes.c_int32
        _lib.PaMacCore_AudioDeviceGetProperty.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_ubyte,
            ctypes.c_uint32,
            POINTER(ctypes.c_uint32),
            c_void_p,
        ]



def _require_lib() -> ctypes.CDLL:
    if _lib is None:
        raise RuntimeError("PortAudio library not available")
    return _lib



def _check_error(err: int):
    if err < 0:
        msg = _require_lib().Pa_GetErrorText(err)
        raise RuntimeError(f"PortAudio error: {msg.decode() if msg else 'Unknown error'}")



def initialize():
    global _initialized
    if not _initialized:
        _check_error(_require_lib().Pa_Initialize())
        _initialized = True




def terminate():
    global _initialized
    if _open_streams:
        return
    if _initialized and _lib is not None:
        _check_error(_require_lib().Pa_Terminate())
        _initialized = False




def has_other_streams(own: "_Stream | None" = None) -> bool:
    return any(stream is not own for stream in _open_streams)



def get_device_count() -> int:
    initialize()
    return _require_lib().Pa_GetDeviceCount()



def get_device_info(index: int) -> dict:
    initialize()
    info_ptr = _require_lib().Pa_GetDeviceInfo(index)
    if not info_ptr:
        raise ValueError(f"Invalid device index: {index}")
    info = info_ptr.contents
    return {
        "index": index,
        "name": info.name.decode("utf-8", errors="replace") if info.name else "",
        "hostApi": info.hostApi,
        "max_input_channels": info.maxInputChannels,
        "max_output_channels": info.maxOutputChannels,
        "default_sample_rate": info.defaultSampleRate,
    }



def get_default_input_device() -> int:
    initialize()
    return _require_lib().Pa_GetDefaultInputDevice()



def get_default_output_device() -> int:
    initialize()
    return _require_lib().Pa_GetDefaultOutputDevice()



def get_input_devices() -> list[dict]:
    initialize()
    devices = []
    for i in range(get_device_count()):
        info = get_device_info(i)
        if info["max_input_channels"] > 0:
            devices.append(info)
    return devices




class _Stream:
    _sample_size = 2

    def __init__(
        self,
        samplerate: int,
        blocksize: int,
        input_params: PaStreamParameters | None = None,
        output_params: PaStreamParameters | None = None,

        blocking: bool = False,

        ring: "_Ring | None" = None,
    ):
        self.samplerate = samplerate
        self._callback_failed = False
        self._stream = c_void_p()
        self._active = False

        if ring:
            self._c_callback = _HELPER_INPUT if input_params else _HELPER_OUTPUT
        else:
            self._c_callback = PaStreamCallback() if blocking else PaStreamCallback(self._pa_callback)

        err = _require_lib().Pa_OpenStream(
            byref(self._stream),
            byref(input_params) if input_params else None,
            byref(output_params) if output_params else None,
            c_double(samplerate),
            c_ulong(blocksize),
            paNoFlag,
            self._c_callback,
            ring.pointer if ring else None,
        )
        _check_error(err)
        _open_streams.add(self)

    def _pa_callback(
        self,
        input_ptr: c_void_p,
        output_ptr: c_void_p,
        frame_count: int,
        time_info: tp.Any,
        status_flags: int,
        user_data: c_void_p,
    ) -> int:
        raise NotImplementedError


    def _callback_error(self):
        if not self._callback_failed:
            self._callback_failed = True
            logging.getLogger("exciton").exception("Audio callback failed")


    def start(self):
        _check_error(_require_lib().Pa_StartStream(self._stream))
        self._active = True


    def stop(self):
        if self._active:
            _check_error(_require_lib().Pa_StopStream(self._stream))
            self._active = False



    def close(self):
        if not self._stream:
            return
        try:
            self.stop()
        except Exception:
            logging.getLogger("exciton").warning("Couldn't stop an audio stream; closing it anyway", exc_info=True)
        _check_error(_require_lib().Pa_CloseStream(self._stream))
        self._active = False
        self._stream = c_void_p()
        _open_streams.discard(self)


    @property
    def active(self) -> bool:
        if self._stream:
            result = _require_lib().Pa_IsStreamActive(self._stream)
            return result == 1
        return False




def _join(thread: threading.Thread | None):
    if thread and thread is not threading.current_thread():
        thread.join(timeout=THREAD_JOIN_SECONDS)


def _running(thread: threading.Thread | None) -> bool:
    return bool(thread and thread.is_alive())




def _free_ring(ring: "_Ring | None", thread: threading.Thread | None):
    if not ring:
        return
    if _running(thread):
        logging.getLogger("exciton").warning("An audio thread outlived its stream; keeping its buffer")
    else:
        ring.free()




def _check_restart(thread: threading.Thread | None):
    if _running(thread):
        raise RuntimeError("The stream's last audio thread is still running")




class _Ring:
    def __init__(self, samplerate: int, frame_bytes: int):
        assert _helper is not None
        self.size = round(RING_SECONDS * samplerate) * frame_bytes
        self._ptr = _helper.exciton_ring_new(self.size, frame_bytes)
        if not self._ptr:
            raise MemoryError("Couldn't make an audio buffer")

    @property
    def pointer(self) -> c_void_p:
        return c_void_p(self._ptr)


    def used(self) -> int:
        return _helper.exciton_ring_used(self._ptr)

    def free_space(self) -> int:
        return _helper.exciton_ring_free_space(self._ptr)


    def overflows(self) -> int:
        return _helper.exciton_ring_overflows(self._ptr)


    def write(self, data: bytes) -> int:
        return _helper.exciton_ring_write(self._ptr, data, len(data))


    def read_into(self, buffer: tp.Any, size: int) -> int:
        return _helper.exciton_ring_read(self._ptr, buffer, size)

    def free(self):
        if self._ptr:
            _helper.exciton_ring_free(self._ptr)
            self._ptr = None








class RawInputStream(_Stream):
    def __init__(
        self,
        samplerate: int = 44100,
        channels: int = 1,
        device: int | None = None,
        callback: tp.Callable[[bytes, int, tp.Any, int], None] | None = None,

        blocksize: int = 1024,
        latency: float = SUGGESTED_LATENCY,

        buffered: bool = True,
    ):
        if blocksize <= 0:
            raise ValueError("An input stream needs a block size")
        initialize()
        self.channels = channels
        self.blocksize = blocksize
        self.device = device if device is not None else get_default_input_device()
        self._user_callback = callback

        self._reader: threading.Thread | None = None
        self._reading = False
        params = PaStreamParameters(
            device=self.device,
            channelCount=channels,
            sampleFormat=paInt16,
            suggestedLatency=latency,
            hostApiSpecificStreamInfo=None,
        )
        self._ring = _Ring(samplerate, channels * self._sample_size) if buffered and _helper else None
        try:
            super().__init__(samplerate, blocksize, input_params=params, blocking=not self._ring, ring=self._ring)
        except Exception:
            if self._ring:
                self._ring.free()
            raise

    @property
    def buffered(self) -> bool:
        return self._ring is not None

    def start(self):
        _check_restart(self._reader)
        super().start()
        self._reading = True
        self._reader = threading.Thread(target=self._read, name="Exciton audio input", daemon=True)
        self._reader.start()


    def stop(self):
        self._reading = False
        _join(self._reader)
        super().stop()

    def close(self):
        super().close()
        if not self._stream:
            _free_ring(self._ring, self._reader)



    def device_buffer_frames(self) -> int | None:
        lib = _require_lib()
        if not self._stream or not hasattr(lib, "PaMacCore_GetStreamInputDevice"):
            return None
        device = lib.PaMacCore_GetStreamInputDevice(self._stream)
        frames = ctypes.c_uint32(0)
        size = ctypes.c_uint32(ctypes.sizeof(frames))
        if not device or lib.PaMacCore_AudioDeviceGetProperty(device, 0, 1, _BUFFER_FRAME_SIZE, byref(size), byref(frames)):
            return None
        return frames.value



    def _read(self):
        lib = _require_lib()
        stream = self._stream
        ring = self._ring
        frames = self.blocksize
        size = frames * self.channels * self._sample_size
        buffer = ctypes.create_string_buffer(size)
        overflows = 0
        while self._reading:
            if ring:
                if ring.used() < size:
                    time.sleep(POLL_SECONDS)
                    continue
                ring.read_into(buffer, size)


                overflowed, overflows = ring.overflows() != overflows, ring.overflows()
            else:
                available = lib.Pa_GetStreamReadAvailable(stream)
                if available < 0:

                    return
                if available < frames:
                    time.sleep(POLL_SECONDS)
                    continue
                err = lib.Pa_ReadStream(stream, buffer, frames)
                if err < 0 and err != paInputOverflowed:
                    return
                overflowed = err == paInputOverflowed
            if self._user_callback:
                try:
                    self._user_callback(buffer.raw, frames, None, paInputOverflow if overflowed else 0)
                except Exception:
                    self._callback_error()








class RawOutputStream(_Stream):
    def __init__(
        self,
        samplerate: int,
        channels: int = 1,
        device: int | None = None,
        callback: tp.Callable[[int], bytes] | None = None,
        blocksize: int = 0,
        latency: float = SUGGESTED_LATENCY,
        buffered: bool = False,
    ):
        initialize()
        self.channels = channels
        self.device = device if device is not None else get_default_output_device()
        self._user_callback = callback

        self._writer: threading.Thread | None = None
        self._writing = False


        self.underflows = 0
        params = PaStreamParameters(
            device=self.device,
            channelCount=channels,
            sampleFormat=paInt16,
            suggestedLatency=latency,
            hostApiSpecificStreamInfo=None,
        )
        self._ring = _Ring(samplerate, channels * self._sample_size) if buffered and _helper else None
        try:
            super().__init__(samplerate, blocksize, output_params=params, ring=self._ring)
        except Exception:
            if self._ring:
                self._ring.free()
            raise

    @property
    def buffered(self) -> bool:
        return self._ring is not None



    def start(self):
        _check_restart(self._writer)
        super().start()
        if self._ring:
            self._writing = True
            self._writer = threading.Thread(target=self._write, name="Exciton audio output", daemon=True)
            self._writer.start()


    def stop(self):
        self._writing = False
        _join(self._writer)
        super().stop()

    def close(self):
        super().close()
        if not self._stream:
            _free_ring(self._ring, self._writer)



    @property
    def queued_seconds(self) -> float:
        if not self._ring or not self._stream:
            return 0.0
        return self._ring.used() / (self.samplerate * self.channels * self._sample_size)



    @property
    def output_latency(self) -> float:
        info = _require_lib().Pa_GetStreamInfo(self._stream) if self._stream else None
        return info.contents.outputLatency if info else 0.0



    def _write(self):
        ring = self._ring
        assert ring is not None
        chunk = WRITE_FRAMES * self.channels * self._sample_size


        fed = False
        while self._writing:
            space = ring.free_space()
            if fed and space == ring.size:
                self.underflows += 1
                fed = False
            if space < chunk:
                time.sleep(POLL_SECONDS)
                continue
            data = self._next_chunk()
            if not data:
                fed = False
                time.sleep(POLL_SECONDS)
                continue
            ring.write(data)
            fed = len(data) == chunk


    def _next_chunk(self) -> bytes:
        frame_bytes = self.channels * self._sample_size
        data = b""
        if self._user_callback:
            try:
                data = self._user_callback(WRITE_FRAMES)[: WRITE_FRAMES * frame_bytes]
            except Exception:
                self._callback_error()
        return data[: len(data) - len(data) % frame_bytes]

    def _pa_callback(
        self,
        input_ptr: c_void_p,
        output_ptr: c_void_p,
        frame_count: int,
        time_info: tp.Any,
        status_flags: int,
        user_data: c_void_p,
    ) -> int:
        if not output_ptr:
            return paContinue
        if status_flags & paOutputUnderflow:
            self.underflows += 1
        byte_count = frame_count * self.channels * self._sample_size
        data = b""
        if self._user_callback:
            try:
                data = self._user_callback(frame_count)[:byte_count]
            except Exception:
                self._callback_error()
        if data:
            ctypes.memmove(output_ptr, data, len(data))
        if len(data) < byte_count:

            ctypes.memset(tp.cast(int, output_ptr) + len(data), 0, byte_count - len(data))
        return paContinue
