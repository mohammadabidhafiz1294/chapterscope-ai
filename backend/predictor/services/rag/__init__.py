"""Phase 4 RAG layer: chunking, embeddings, storage and retrieval.

Public entry points:

* :mod:`predictor.services.rag.indexing` -- ``sync_chunks``, ``embed_pending``
  and ``index_notebook``.
* :mod:`predictor.services.rag.retrieval` -- ``search``.
* :mod:`predictor.services.rag.schema`` -- ``ensure_vector_schema``,
  ``require_ready`` and ``vector_status``.
* :mod:`predictor.services.rag.errors`` -- the error taxonomy the API maps to
  HTTP status codes.
"""
