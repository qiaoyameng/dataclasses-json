# flake8: noqa
from dataclasses_json.api import (DataClassJsonMixin,
                                  dataclass_json)
from dataclasses_json.cfg import (config, global_config,
                                  Exclude, LetterCase,
                                  MAX_SAFE_INTEGER, MAX_COMPAT_INTEGER)
from dataclasses_json.undefined import CatchAll, Undefined

from dataclasses_json.__version__ import __version__

__all__ = ['DataClassJsonMixin', 'LetterCase', 'dataclass_json',
           'config', 'global_config', 'Exclude',
           'MAX_SAFE_INTEGER', 'MAX_COMPAT_INTEGER',
           'CatchAll', 'Undefined']
