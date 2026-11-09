"""Checked edits that do not commit unrelated edits owned by the user."""
from contextlib import contextmanager


@contextmanager
def edit_layer(layer, title):
    owns = not layer.isEditable()
    if owns and not layer.startEditing():
        raise ValueError(f'Layer non modificabile: {layer.name()}')
    layer.beginEditCommand(title)
    try:
        yield
        layer.endEditCommand()
        if owns and not layer.commitChanges():
            errors = '; '.join(layer.commitErrors())
            layer.rollBack()
            raise ValueError(f'Scrittura non riuscita: {errors}')
    except Exception:
        if layer.isEditable():
            if owns:
                layer.rollBack()
            elif layer.isEditCommandActive():
                layer.destroyEditCommand()
        raise


def checked(result, message):
    if not result:
        raise ValueError(message)
