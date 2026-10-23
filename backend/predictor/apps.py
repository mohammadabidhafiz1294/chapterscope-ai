from django.apps import AppConfig


class PredictorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'predictor'

    def ready(self):
        # Keep the pgvector schema in step with EMBEDDING_DIMENSION and with a
        # SQLite -> PostgreSQL switch. The handler is guarded so `migrate` can
        # never fail because of RAG schema setup.
        from django.db.models.signals import post_migrate

        from .services.rag.schema import ensure_on_migrate

        post_migrate.connect(ensure_on_migrate, sender=self)
