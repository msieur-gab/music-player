"""Remote Control addon — no backend routes, UI-only."""


def register(ctx):
    """No routes needed — the remote page is served as static HTML."""
    return {}
