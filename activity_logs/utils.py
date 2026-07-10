from core.middleware import get_current_request


def get_request():
    """Get the current request object from thread-local storage."""
    return get_current_request()


def get_client_ip(request=None):
    """Get the client's IP address from the request."""
    if request is None:
        request = get_request()
    if not request:
        return None
    return request.META.get("REMOTE_ADDR")