import typing as tp
from ... import utils
from .. import td



class SummonBase:
    def __init__(self, id: str, on_resolve: tp.Callable[[td.SummonResponse], None]):
        self.id = id
        self.status: tp.Literal["running", "resolved", "rejected"] = "running"
        self._on_resolve = on_resolve


    def run(self):
        raise NotImplementedError

    def resolve(self, result: str | None = None, *, state: bool | None = None):
        if self.is_done:
            return
        self.status = "resolved"
        reply = self._build_reply(result=result)
        if state is not None:
            reply["state"] = state
        self._on_resolve(reply)

    def reject(self, error: str | None = None):
        if self.is_done:
            return
        self.status = "rejected"
        utils.logger.info("Summon %s failed: %s", self.id, error)
        self._on_resolve(self._build_reply(error=error))

    @property
    def is_done(self):
        return self.status != "running"



    def _build_reply(self, result: str | None = None, error: str | None = None) -> td.SummonResponse:
        if self.status == "resolved":
            return {"status": "OK", "result": result, "logs": []}
        return {"status": "ERROR", "error": error, "logs": []}
