from contextlib import asynccontextmanager


@asynccontextmanager
async def tracing_span(langfuse, display_name: str, session_id: str):
    """
    Async context manager that opens a Langfuse span for the duration of the
    block and sets propagate_attributes so child observations inherit the
    session_id. Yields the span (or None if langfuse is None). The span stays
    open while the caller streams the graph, reads final state, and calls
    span.update() — then closes on __aexit__.
    """
    if langfuse:
        from langfuse import propagate_attributes

        with langfuse.start_as_current_span(name=display_name) as span:
            with propagate_attributes(session_id=session_id):
                yield span
    else:
        yield None
