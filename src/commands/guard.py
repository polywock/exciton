import json
import os
import re
import typing as tp



with open(os.path.join(os.path.dirname(__file__), "exclusions.json"), encoding="utf-8") as _file:
    _EXCLUSIONS = json.load(_file)

_OPERATORS = frozenset(_EXCLUSIONS["operators"])
_PROPERTIES = frozenset(_EXCLUSIONS["properties"])
_OPERATOR_PROPERTIES = {op: frozenset(props) for op, props in _EXCLUSIONS["operatorProperties"].items()}


_PATH_PROPERTIES = frozenset(_EXCLUSIONS["pathProperties"])
_PLAIN_PATH = re.compile(_EXCLUSIONS["plainPath"], re.ASCII)



def refusal(operator: str, props: dict[str, tp.Any]) -> str | None:
    if operator in _OPERATORS:
        return f"{operator} is excluded"
    for key, value in props.items():
        if key in _PROPERTIES or key in _OPERATOR_PROPERTIES.get(operator, ()):
            return f"{operator}'s {key} is excluded"
        if key in _PATH_PROPERTIES and value and not (isinstance(value, str) and _PLAIN_PATH.fullmatch(value)):
            return f"{operator}'s {key} isn't a plain property path"
    return None
