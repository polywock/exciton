


import typing as tp


portaudio_error: str | None = None

if tp.TYPE_CHECKING:
    from . import portaudio
else:
    try:
        from . import portaudio

        if not portaudio.available:
            portaudio_error = "library not found"
    except Exception as e:
        portaudio = None
        portaudio_error = f"{type(e).__name__}: {e}"


def portaudio_available() -> bool:
    return portaudio is not None and portaudio.available
