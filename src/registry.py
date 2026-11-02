import typing as tp

if tp.TYPE_CHECKING:
    from .overseer import Overseer as OverseerType
    from .ribbon import Ribbon as RibbonType
    from .api.channel import Channel as ChannelType
    from .overlay import Overlay as OverlayType

Overseer: "type[OverseerType]"
Ribbon: "type[RibbonType]"
Channel: "type[ChannelType]"
Overlay: "type[OverlayType]"


def set_overseer(oss: "type[OverseerType]"):
    global Overseer, Ribbon, Channel, Overlay
    Overseer = oss
    Ribbon = oss.ribbon.Ribbon
    Channel = oss.channel.Channel
    Overlay = oss.overlay.Overlay
