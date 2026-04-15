from django.core.management.base import BaseCommand
from apps.books.models import Book, Chapter, Chunk, Summary, Flashcard


class Command(BaseCommand):
    help = 'Seeds the database with sample book data matching the Flutter mock data'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding books...')

        # ── Atomic Habits ──────────────────────────────────────────────
        book, _ = Book.objects.get_or_create(
            title='Atomic Habits',
            defaults={
                'author': 'James Clear',
                'cover_image_url': 'https://covers.openlibrary.org/b/isbn/9780735211292-L.jpg',
                'category': 'Self-Improvement',
                'readers_count': 3_000_000,
                'rating': 4.8,
                'has_audio': False,
                'description': 'An easy & proven way to build good habits & break bad ones.',
                'total_chapters': 10,
                'pages_left': 185,
                'flashcards_count': 5,
                'read_per_day_minutes': 45,
                'is_published': True,
                'is_trending': True,
                'is_recommended': True,
                'badge': '#1',
            }
        )

        # Chapters
        chapters_data = [
            (1, 'The Surprising Power of Atomic Habits', 'Pages 15-25', 18, False),
            (2, 'How Your Habits Shape Your Identity', 'Pages 26-42', 22, False),
            (3, 'How to Build Better Habits in 4 Simple Steps', 'Pages 43-65', 25, False),
            (4, "The Man Who Didn't Look Right", 'Pages 66-82', 20, False),
            (5, 'The Best Way to Start a New Habit', 'Pages 83-105', 24, False),
        ]

        for num, title, page_range, duration, is_locked in chapters_data:
            chapter, _ = Chapter.objects.get_or_create(
                book=book,
                chapter_number=num,
                defaults={
                    'title': title,
                    'page_range': page_range,
                    'duration_in_minutes': duration,
                    'is_locked': is_locked,
                }
            )

            # Add 5 chunks per chapter
            for i in range(5):
                Chunk.objects.get_or_create(
                    chapter=chapter,
                    chunk_index=i,
                    defaults={
                        'text': f'This is chunk {i + 1} of {title}. '
                                f'It contains key insights from this chapter that are '
                                f'broken into manageable reading sessions.',
                        'estimated_minutes': 2,
                    }
                )

            # Add summary for first 3 chapters
            if num <= 3:
                Summary.objects.get_or_create(
                    chapter=chapter,
                    defaults={
                        'title': title,
                        'summary_content': f'Chapter {num} explores key concepts around habit formation.',
                        'key_takeaways': [
                            'Focus on systems, not on goals',
                            'Habits are the compound interest of self-improvement',
                            'A 1% improvement every day yields huge results over a year',
                        ],
                        'is_locked': num > 3,
                    }
                )

        # Flashcards
        flashcards_data = [
            (
                'What is the "Compound Interest" of self-improvement?',
                'Habits. A 1% improvement everyday yields huge results over a year.'
            ),
            (
                'What is the most effective way to change your habits?',
                'Focus not on what you want to achieve, but on WHO you wish to become.'
            ),
            (
                'What are the 4 simple steps to build better habits?',
                'Cue, Craving, Response, and Reward.'
            ),
            (
                'What is an "Implementation Intention"?',
                'A plan you make beforehand about when and where to act.'
            ),
            (
                'What plays a bigger role: Motivation or Environment?',
                'Environment often matters more. Make the cues of good habits obvious.'
            ),
        ]

        for question, answer in flashcards_data:
            Flashcard.objects.get_or_create(
                book=book,
                question=question,
                defaults={'answer': answer}
            )

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created: {book.title} with chapters, chunks, summaries, flashcards.'
        ))