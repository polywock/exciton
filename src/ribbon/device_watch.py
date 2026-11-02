









import ctypes
import struct
import sys
import typing as tp

Fingerprint: tp.TypeAlias = tuple



def fingerprint() -> Fingerprint | None:
    try:
        if sys.platform == "darwin":
            return _macos()
        if sys.platform == "win32":
            return _windows()
        if sys.platform.startswith("linux"):
            return _linux()
    except Exception:
        return None
    return None





_CoreAudio: tp.Any = None
_SYSTEM_OBJECT = 1


class _PropertyAddress(ctypes.Structure):
    _fields_ = [("mSelector", ctypes.c_uint32), ("mScope", ctypes.c_uint32), ("mElement", ctypes.c_uint32)]


def _fourcc(code: str) -> int:
    return struct.unpack(">I", code.encode())[0]


def _core_audio():
    global _CoreAudio
    if _CoreAudio is None:
        lib = ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        size_fn = lib.AudioObjectGetPropertyDataSize
        size_fn.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(_PropertyAddress),
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        size_fn.restype = ctypes.c_int32
        data_fn = lib.AudioObjectGetPropertyData
        data_fn.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(_PropertyAddress),
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        ]
        data_fn.restype = ctypes.c_int32
        _CoreAudio = lib
    return _CoreAudio



def _core_audio_ids(selector: str) -> tuple[int, ...]:
    lib = _core_audio()
    address = _PropertyAddress(_fourcc(selector), _fourcc("glob"), 0)
    size = ctypes.c_uint32(0)
    if lib.AudioObjectGetPropertyDataSize(_SYSTEM_OBJECT, ctypes.byref(address), 0, None, ctypes.byref(size)) != 0:
        raise OSError(f"CoreAudio couldn't size {selector!r}")
    ids = (ctypes.c_uint32 * max(1, size.value // 4))()
    if lib.AudioObjectGetPropertyData(_SYSTEM_OBJECT, ctypes.byref(address), 0, None, ctypes.byref(size), ids) != 0:
        raise OSError(f"CoreAudio couldn't read {selector!r}")

    return tuple(ids[: size.value // 4])


def _macos() -> Fingerprint:

    return (_core_audio_ids("dev#"), _core_audio_ids("dIn "), _core_audio_ids("dOut"))





_MAXPNAMELEN = 32
_WAVE_MAPPER = 0xFFFFFFFF
_DRVM_MAPPER_PREFERRED_GET = 0x2015


class _WaveInCaps(ctypes.Structure):
    _fields_ = [
        ("wMid", ctypes.c_uint16),
        ("wPid", ctypes.c_uint16),
        ("vDriverVersion", ctypes.c_uint32),
        ("szPname", ctypes.c_wchar * _MAXPNAMELEN),
        ("dwFormats", ctypes.c_uint32),
        ("wChannels", ctypes.c_uint16),
        ("wReserved1", ctypes.c_uint16),
    ]


class _WaveOutCaps(ctypes.Structure):
    _fields_ = [*_WaveInCaps._fields_, ("dwSupport", ctypes.c_uint32)]


def _windows() -> Fingerprint:
    winmm = ctypes.WinDLL("winmm")
    return (
        _wave_names(winmm.waveInGetNumDevs, winmm.waveInGetDevCapsW, _WaveInCaps),
        _wave_names(winmm.waveOutGetNumDevs, winmm.waveOutGetDevCapsW, _WaveOutCaps),
        _wave_preferred(winmm.waveInMessage),
        _wave_preferred(winmm.waveOutMessage),
    )


def _wave_names(count_fn, caps_fn, caps_type) -> tuple[str, ...]:
    count_fn.restype = ctypes.c_uint
    caps_fn.argtypes = [ctypes.c_size_t, ctypes.POINTER(caps_type), ctypes.c_uint]
    caps_fn.restype = ctypes.c_uint
    names = []
    for i in range(count_fn()):
        caps = caps_type()
        error = caps_fn(i, ctypes.byref(caps), ctypes.sizeof(caps))
        names.append(caps.szPname if error == 0 else f"<error {error}>")
    return tuple(names)



def _wave_preferred(message_fn) -> int | None:
    message_fn.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
    message_fn.restype = ctypes.c_uint
    device, flags = ctypes.c_uint32(), ctypes.c_uint32()
    if message_fn(_WAVE_MAPPER, _DRVM_MAPPER_PREFERRED_GET, ctypes.byref(device), ctypes.byref(flags)) != 0:
        return None
    return device.value




_ASOUND_CARDS = "/proc/asound/cards"


def _linux() -> Fingerprint:
    with open(_ASOUND_CARDS, encoding="utf-8", errors="replace") as f:
        return (f.read(),)
