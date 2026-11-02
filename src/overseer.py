from . import utils
from . import configs
from . import shortcut
from .api import snapshot
from . import ribbon
from . import registry
from .api import channel
from .ribbon import connection as ribbon_connection
from . import overlay
from . import types



def is_debug_mode(config: types.Config) -> bool:
    return bool((config.get("snapshot") or {}).get("debugMode"))


class Overseer:
    ribbon = ribbon
    channel = channel
    overlay = overlay


    _synced_snapshot_id: str | None = None
    _channel_wanted = False

    @classmethod
    def pre_register(cls):
        registry.set_overseer(cls)
        configs._ensure_loaded()

    @classmethod
    def register(cls):
        overlay.Overlay.register()
        if not ribbon.audio.portaudio_available():
            utils.logger.warning("PortAudio unavailable, voice input won't work: %s", ribbon.audio.portaudio_error)
        shortcut.clear_keymaps_for_launch(cls.on_init_complete)

    @classmethod
    def on_init_complete(cls):
        data = configs.get_config()
        data["_init_complete"] = True
        utils.logger.info("Init complete (signed in: %s, online access: %s)", bool(data.get("token")), utils.allows_internet())

        if data.get("token") and utils.allows_internet():
            cls.on_signed_in()

    @classmethod
    def unregister(cls):
        overlay.Overlay.unregister()
        utils.clear_timers()
        shortcut.clear_keymaps()

        cls._synced_snapshot_id = None
        cls._channel_wanted = False
        ribbon.Ribbon.cancel_all()
        ribbon.recorder.Recorder.shutdown()
        configs.close()
        channel.Channel.disconnect()
        ribbon_connection.Spare.keep(None)

    @classmethod
    def on_signed_in(cls):
        snapshot.api_snapshot_rl()

    @classmethod
    def sign_out(cls):
        utils.logger.info("Signing out")
        config = configs.get_config()
        config["token"] = None
        config["snapshot"] = None
        config["_active_snapshot"] = None
        config["_snapshot_loading_latest"] = None
        configs.persist()
        cls.sync()

    @classmethod
    def sync(cls):
        config = configs.get_config()
        cls.sync_shortcuts(config)
        cls.sync_channel(config)
        utils.redraw_panel()

    @classmethod
    def sync_shortcuts(cls, config: types.Config):
        allowed = config.get("token") and config.get("_active_snapshot") and utils.allows_internet()

        ribbon_connection.Spare.keep(config.get("token") if allowed else None)
        if allowed:
            snapshot_id = (config.get("_active_snapshot") or {}).get("id") or ""
            if not snapshot_id or snapshot_id != cls._synced_snapshot_id:
                cls._synced_snapshot_id = snapshot_id
                shortcut.sync_keymaps(False)
        elif cls._synced_snapshot_id is not None:
            cls._synced_snapshot_id = None
            shortcut.clear_keymaps()


    @classmethod
    def force_shortcut_resync(cls):
        cls._synced_snapshot_id = None

    @classmethod
    def sync_channel(cls, config: types.Config):
        if config.get("token") and utils.allows_internet():
            if not cls._channel_wanted or not channel.Channel.is_open():
                cls._channel_wanted = True
                channel.Channel.connect(config.get("token"))
        elif cls._channel_wanted:
            cls._channel_wanted = False
            channel.Channel.disconnect()
