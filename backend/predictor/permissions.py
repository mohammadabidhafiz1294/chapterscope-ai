from rest_framework.permissions import BasePermission


class IsNotebookOwner(BasePermission):
    """Object-level permission: the user must own the notebook.

    Accepts either a CourseNotebook instance (has owner_id) or any object that
    exposes a ``notebook`` attribute (Question, ChatSession, Syllabus,
    ExamPaper, ...). Defence-in-depth on top of owner-scoped querysets, which
    remain the primary access control (cross-user objects are never fetched).
    """

    message = 'You do not own this notebook.'

    def has_permission(self, request, view):
        # View-level gate; object scoping happens in get_queryset/get_object.
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        owner_id = getattr(obj, 'owner_id', None)
        if owner_id is not None:
            return owner_id == request.user.id
        notebook = getattr(obj, 'notebook', None)
        if notebook is not None:
            return notebook.owner_id == request.user.id
        return False
