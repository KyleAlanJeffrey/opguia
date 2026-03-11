"""Base classes for NiceGUI pages and components with managed task/timer lifecycle.

asyncio only holds *weak* references to tasks created with create_task(), so
tasks can be garbage-collected between sleep intervals unless a strong reference
is kept elsewhere. PageContext holds those references and provides a consistent
API for spawning tasks and creating timers.

Usage in a page handler:
    ctx = PageContext()
    ctx.spawn(my_background_loop())          # tracked, GC-safe
    ctx.timer(5.0, my_callback)              # same API as ui.timer
    ctx.replace_task(slot, my_loop())        # cancel old task, spawn new one

Usage in a component class:
    class MyPanel(Component):
        def build(self):
            self.spawn(self.poll())          # delegates to ctx
            self.timer(1.0, self.refresh)
"""

import asyncio
from nicegui import ui


class PageContext:
    """Instantiated once per page visit. Holds strong refs to background tasks."""

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, coro) -> asyncio.Task:
        """Create a tracked asyncio task. Prevents GC between sleep intervals."""
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    def timer(self, interval: float, callback, *, once: bool = False) -> ui.timer:
        """Create a ui.timer. NiceGUI holds its own strong ref; method is here
        for a consistent API so all background activity goes through one place."""
        return ui.timer(interval, callback, once=once)

    def replace_task(self, slot: list, coro) -> asyncio.Task:
        """Cancel the task in slot[0] (if any) and spawn a replacement.

        Use a one-element list as a mutable slot so closures can share it:
            _slot: list[asyncio.Task] = []
            ctx.replace_task(_slot, my_loop())
        """
        if slot:
            slot[0].cancel()
            slot.clear()
        t = self.spawn(coro)
        slot.append(t)
        return t

    def cleanup(self):
        """Cancel all tracked tasks (e.g. on page teardown)."""
        for t in list(self._tasks):
            t.cancel()
        self._tasks.clear()


class Component:
    """Base class for NiceGUI components that participate in a page's lifecycle.

    Subclass this and pass the page's PageContext so all background activity
    from the component is tracked alongside the page's own tasks.

    class MyPanel(Component):
        def __init__(self, ctx: PageContext, client):
            super().__init__(ctx)
            self.client = client

        def build(self):
            self.spawn(self._poll())
            self.timer(5.0, self._refresh)
    """

    def __init__(self, ctx: PageContext):
        self.ctx = ctx

    def spawn(self, coro) -> asyncio.Task:
        return self.ctx.spawn(coro)

    def timer(self, interval: float, callback, *, once: bool = False) -> ui.timer:
        return self.ctx.timer(interval, callback, once=once)

    def replace_task(self, slot: list, coro) -> asyncio.Task:
        return self.ctx.replace_task(slot, coro)
