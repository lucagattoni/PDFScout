MODEL = "claude-sonnet-4-6"
CONCURRENCY_LIMIT = 3  # asyncio.Semaphore cap across parallel burst page invocations
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper"}
FALLBACK_DOC_TYPE = "baseline_core"
COLUMN_BUCKET_PX = 50  # xmin bucket width for geometric pre-sorter column grouping
