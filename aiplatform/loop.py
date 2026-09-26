"""Run a coroutine from a Lambda handler without disturbing the event loop Mangum keeps."""

import asyncio
import warnings


def run_preserving_loop(coro):
    """asyncio.run() that leaves the previously current event loop current again afterwards.

    asyncio.run() closes its own loop and clears the current one. Mangum keeps ONE loop across warm
    invocations and the shared SQLAlchemy pool is bound to it: having no loop breaks Mangum
    ("There is no current event loop"), having a *different* one breaks pooled connections
    ("attached to a different loop"). Restoring the same loop avoids both.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            previous = asyncio.get_event_loop_policy().get_event_loop()
        except RuntimeError:
            previous = None
    try:
        return asyncio.run(coro)
    finally:
        usable = previous is not None and not previous.is_closed()
        asyncio.set_event_loop(previous if usable else asyncio.new_event_loop())
