"""The extraction layer.

Split by job: `service` queues a run, `registry` and `router` decide what to ask
the model, `prompts` and `client` do the asking, `runner` validates and retries,
`defaults` covers everything computable without a model, and `worker` stitches
it all into a contract and a draft incident.

Nothing is re-exported here on purpose. The celery task imports the worker and
the service imports the task, so a package-level import of either would close
that loop at import time. Import the submodule you need.
"""
