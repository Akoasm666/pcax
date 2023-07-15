__all__ = ["Module", "EnergyModule"]

import jax
import jax.tree_util as jt

from ..core import Module, ParamCache
from ..core.parameters import _BaseParam
from .parameters import NodeParam


class EnergyModule(Module):
    def __init__(self) -> None:
        super().__init__()
        self._init = False
        self._status = None

    def clear_cache(self):
        parameters = jax.tree_util.tree_leaves(self, is_leaf=lambda x: isinstance(x, _BaseParam))
        for p in parameters:
            if isinstance(p, ParamCache):
                p.clear()

    def clear_nodes(self):
        parameters = jax.tree_util.tree_leaves(self, is_leaf=lambda x: isinstance(x, _BaseParam))
        for p in parameters:
            if isinstance(p, NodeParam):
                p.value = None

    def energy(self):
        return jt.tree_reduce(
            lambda x, y: x + y,
            tuple(m.energy() for m in self.get_submodules(cls=EnergyModule)),
        )

    def set_status(self, **status):
        if "init" in status:
            self._init = status["init"]

        for m in self.get_submodules(cls=EnergyModule):
            m.set_status(**status)

    @property
    def is_init(self):
        return self._init is True