from typing import Union, Any, Callable, Hashable, Mapping
import jax
import jax.tree_util as jtu
import optax

ReduceSate = optax.EmptyState


def reduce(
    axis_name="AX_BATCH",
    reduce_fn=jax.lax.pmean,
) -> optax.GradientTransformation:
    def init_fn(params):
        del params
        return optax.ReduceState(axis_name)

    def update_fn(updates, state, params=None):
        del params
        updates = reduce_fn(updates, axis_name)
        return updates, state

    return optax.GradientTransformation(init_fn, update_fn)


def multi_transform(
    transforms: Mapping[Hashable, optax.GradientTransformation],
    param_labels: Union[Any, Callable[[Any], Any]],
) -> optax.GradientTransformation:
    def init_fn(params, state=None, group_filter=None):
        labels = param_labels(params) if callable(param_labels) else param_labels

        label_set = set(jax.tree_util.tree_leaves(labels))
        if not label_set.issubset(transforms.keys()):
            raise ValueError(
                "Some parameters have no corresponding transformation.\n"
                f"Parameter labels: {list(sorted(label_set))} \n"
                f"Transforms keys: {list(sorted(transforms.keys()))} \n"
            )
        if state is not None and group_filter is not None:
            # Initialize only the groups specified by group_filter, otherwise keep the existing state
            inner_states = {
                group: (
                    optax.masked(tx, make_mask(labels, group)).init(params)
                    if group in group_filter
                    else state[group]
                )
                for group, tx in transforms.items()
            }
        else:
            # Initialize the state from scratch
            inner_states = {
                group: optax.masked(tx, make_mask(labels, group)).init(params)
                for group, tx in transforms.items()
            }
        return optax.MultiTransformState(inner_states)

    def make_mask(labels, group):
        return jax.tree_util.tree_map(lambda label: label == group, labels)

    def update_fn(updates, state, params=None):
        labels = param_labels(updates) if callable(param_labels) else param_labels
        new_inner_state = {}
        for group, tx in transforms.items():
            group_mask = make_mask(labels, group)
            update_group = not jtu.tree_all(
                jtu.tree_map(lambda m, v: m == False or v is None, group_mask, updates)
            )

            if update_group:
                masked_tx = optax.masked(tx, group_mask)
                updates, new_inner_state[group] = masked_tx.update(
                    updates, state.inner_states[group], params
                )
            else:
                updates, new_inner_state[group] = updates, state.inner_states[group]
        return updates, optax.MultiTransformState(new_inner_state)

    """def update_fn(updates, state, params=None):
        labels = param_labels(updates) if callable(param_labels) else param_labels
        new_inner_state = {}
        
        for group, tx in transforms.items():
            group_mask = make_mask(labels, group)
            update_group = not jtu.tree_all(jtu.tree_map(lambda m, v: m == False or v is None, group_mask, updates))
            masked_tx = optax.masked(tx, group_mask)

            def do_update(_):
                return masked_tx.update(updates, state.inner_states[group], params)

            def reject_update(_):
                return updates, state.inner_states[group]

            updates, new_inner_state[group] = jax.lax.cond(update_group, 
                do_update,
                reject_update,
                operand=None
            )
            
        return updates, optax.MultiTransformState(new_inner_state)
    """

    return optax.GradientTransformation(init_fn, update_fn)
