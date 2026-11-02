from .src import shortcut
from .src import overseer
from .src import bespoke
from .src import panel
from .src import utils
from .src.ribbon.summons import confirm
from .src.ribbon.summons import pointer
from .src.ribbon.summons import watch


def register():
    utils.setup_logging()
    overseer.Overseer.pre_register()
    shortcut.register()
    panel.register()
    bespoke.register()
    confirm.register()
    watch.register()
    overseer.Overseer.register()


def unregister():
    overseer.Overseer.unregister()
    pointer.unregister()
    watch.unregister()
    confirm.unregister()
    bespoke.unregister()
    panel.unregister()
    shortcut.unregister()
    utils.logger.info("Unregistered")
    utils.teardown_logging()
