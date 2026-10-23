"""Phase 6 notebook chat: a deterministic LangChain pipeline over RAG.

Public entry points:

* :mod:`predictor.services.chat.pipeline` -- ``respond`` orchestrates one
  turn: validate -> resolve model (fail fast, no write) -> load bounded
  history -> persist the user message -> notebook-filtered retrieval ->
  model call -> strict JSON validation -> citation filtering -> persist the
  assistant message.
* :mod:`predictor.services.chat.model` -- ``get_chat_model`` lazily builds
  the LangChain ``ChatGoogleGenerativeAI`` client.
* :mod:`predictor.services.chat.errors` -- the error taxonomy the API maps
  to HTTP status codes.

Grounding rules: every citation must name a ``source_key`` returned by the
current retrieval pass; all display fields are rebuilt server-side from that
pass. History, retrieved documents and the user question are untrusted data
passed as delimited prompt blocks; no tools are bound and no hidden
reasoning is stored. Tests never call a real provider.
"""
