"""Build and embed DocumentChunk rows (Phase 4 RAG indexing).

    manage.py index_rag                      # every notebook
    manage.py index_rag --notebook 3         # one notebook
    manage.py index_rag --sync-only          # chunk rows only (no network)
    manage.py index_rag --reset-vectors      # drop vectors, queue re-embedding
    manage.py index_rag --strict             # exit non-zero on any failure

Chunking is portable and runs on SQLite too; embedding needs PostgreSQL +
pgvector + a configured provider and reports honestly when either is missing.
"""

from django.core.management.base import BaseCommand, CommandError

from predictor.models import CourseNotebook
from predictor.services.rag import indexing
from predictor.services.rag.errors import RAGError


class Command(BaseCommand):
    help = 'Sync (and optionally embed) retrievable chunks for course notebooks.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--notebook', type=int, default=None,
            help='Limit indexing to one course notebook id.',
        )
        parser.add_argument(
            '--sync-only', action='store_true',
            help='Create/update chunk rows without calling the embedding provider.',
        )
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Embed at most N pending chunks this run.',
        )
        parser.add_argument(
            '--reset-vectors', action='store_true',
            help='Delete every stored vector and queue all chunks for re-embedding.',
        )
        parser.add_argument(
            '--strict', action='store_true',
            help='Fail the command if embedding reports any error.',
        )

    def handle(self, *args, **options):
        if options['reset_vectors']:
            self._reset()

        notebooks = CourseNotebook.objects.all().order_by('pk')
        if options['notebook'] is not None:
            notebooks = notebooks.filter(pk=options['notebook'])
            if not notebooks.exists():
                raise CommandError(
                    f'CourseNotebook {options["notebook"]} does not exist.'
                )

        totals = {'created': 0, 'updated': 0, 'unchanged': 0, 'deleted': 0,
                  'chunks': 0, 'embedded': 0, 'failed': 0}
        failure_codes = []

        for notebook in notebooks:
            try:
                sync = indexing.sync_chunks(notebook)
            except RAGError as exc:
                raise CommandError(f'{exc.code}: {exc.message}')

            if options['sync_only']:
                embed = {'skipped': 'sync_only'}
            else:
                try:
                    embed = indexing.embed_pending(
                        notebook,
                        limit=options['limit'],
                        raise_on_error=options['strict'],
                    )
                except RAGError as exc:
                    raise CommandError(f'{exc.code}: {exc.message}')

            for key in totals:
                totals[key] += sync.get(key, 0) + embed.get(key, 0)
            failure_codes.extend(embed.get('errors', []))

            line = (
                f'notebook={notebook.pk} chunks={sync["chunks"]} '
                f'created={sync["created"]} updated={sync["updated"]} '
                f'deleted={sync["deleted"]} embedded={embed.get("embedded", 0)} '
                f'failed={embed.get("failed", 0)}'
            )
            if embed.get('skipped'):
                line += f' embed_skipped={embed["skipped"]}'
            if embed.get('failed'):
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(line)

        self.stdout.write(
            'total chunks={chunks} created={created} updated={updated} '
            'deleted={deleted} embedded={embedded} failed={failed}'.format(
                **totals
            )
        )
        if failure_codes:
            codes = ', '.join(sorted(set(failure_codes)))
            message = f'Embedding reported errors: {codes}'
            if options['strict']:
                raise CommandError(message)
            self.stdout.write(self.style.WARNING(message))

    def _reset(self):
        result = indexing.reset_vectors()
        self.stdout.write(f'reset_vectors {result}')
        if result.get('skipped') == 'not_postgres':
            raise CommandError(
                'Vector reset needs PostgreSQL with pgvector (DATABASE_URL).'
            )
