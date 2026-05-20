"""
seed_demo.py — Wipe DB and seed User 1: Shahzaib Ali
Run: python manage.py seed_demo
"""
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

User = get_user_model()

# Book data dicts — populated at bottom of file
THINK_GROW_RICH   = {}
MANS_SEARCH       = {}
ART_OF_HAPPINESS  = {}
ART_OF_WAR        = {}
RICHEST_MAN       = {}
AS_A_MAN_THINKETH = {}
LETTERS_STOIC     = {}
SCIENCE_RICH      = {}


class Command(BaseCommand):
    help = "Wipe DB and seed demo data for all 3 demo users"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Clearing database..."))
        self._clear_db()
        self.stdout.write("Creating superuser...")
        self._create_superuser()
        self.stdout.write("Creating Shahzaib Ali...")
        shahzaib = self._create_shahzaib()
        self.stdout.write("Creating admin books...")
        admin_books = self._create_admin_books()
        self.stdout.write("Setting up library...")
        self._setup_library(shahzaib, admin_books)
        self.stdout.write("Creating uploads...")
        upload_books = self._create_uploads(shahzaib)
        self.stdout.write("Creating intelligence data...")
        all_books = list(admin_books.values()) + upload_books
        self._create_intelligence(shahzaib, all_books)
        self.stdout.write("Creating community...")
        self._create_community(shahzaib, admin_books)
        self.stdout.write("Creating Q&A...")
        self._create_qa(shahzaib, admin_books)
        self.stdout.write("Creating notifications...")
        self._create_notifications(shahzaib, all_books)
        self.stdout.write("Creating Aroona Bibi...")
        aroona = self._create_aroona()
        self.stdout.write("Setting up Aroona library...")
        self._setup_library_aroona(aroona, admin_books, upload_books)
        self.stdout.write("Creating Aroona community & Q&A...")
        self._create_community_aroona(aroona, admin_books)
        self._create_qa_aroona(aroona, admin_books)
        self._create_notifications_aroona(aroona, all_books)
        self.stdout.write("Creating Sana Zia...")
        sana = self._create_sana()
        self.stdout.write("Setting up Sana library...")
        self._setup_library_sana(sana, admin_books)
        self.stdout.write("Creating Sana community & Q&A...")
        self._create_community_sana(sana, admin_books)
        self._create_qa_sana(sana, admin_books)
        self._create_notifications_sana(sana, all_books)
        self.stdout.write(self.style.SUCCESS("Demo seed complete — 3 users seeded!"))

    def _clear_db(self):
        from django.db import connection
        # Wipe ALL orphaned tables whose names start with known legacy prefixes
        # (they hold FK references to users_user but have no registered models).
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE 'discussions\_%' ESCAPE '\\'
                ORDER BY table_name DESC
                """
            )
            disc_tables = [row[0] for row in cursor.fetchall()]
            for table in disc_tables:
                cursor.execute(f'DELETE FROM "{table}"')

        from django.apps import apps as django_apps
        order = [
            "book_intelligence.QAMessage", "book_intelligence.QAConversation",
            "book_intelligence.NotificationContent", "book_intelligence.PageEmbedding",
            "book_intelligence.ChapterIntelligence", "book_intelligence.BookIntelligenceChapter",
            "book_intelligence.BookIntelligenceProfile",
            "community.MessageReaction", "community.Message",
            "community.CommunityMember", "community.Community",
            "reading.ReadingSession", "reading.ReadingPlan",
            "library.ChapterProgress", "library.UserBook",
            "books.ReadingSchedule", "books.Flashcard", "books.Summary",
            "books.Chunk", "books.Chapter", "books.UserUploadedBook", "books.Book",
            "users.PasswordResetOTP", "users.User",
        ]
        for label in order:
            app, model = label.split(".")
            django_apps.get_model(app, model).objects.all().delete()

    def _create_superuser(self):
        User.objects.create_superuser(
            email="shahzaib8157@gmail.com",
            password="Shebii@1290",
            full_name="Shahzaib (Admin)",
        )

    def _create_shahzaib(self):
        user = User.objects.create_user(
            email="shahzaibali5077@gmail.com",
            password="Shaibiali@1290",
            full_name="Shahzaib Ali",
            books_read=3,
            total_pages_read=847,
            current_streak=9,
            is_avid_reader=True,
        )
        from apps.reading.models import ReadingPlan
        ReadingPlan.objects.create(user=user, pages_per_day=10, days_per_week=6, preferred_time="Evening")
        return user

    def _make_book(self, data, source):
        from apps.books.models import Book, Chapter, Chunk, Summary, Flashcard
        from apps.books.cover_service import fetch_cover_image_url
        cover_url = data.get("cover_image_url", "") or ""
        if not cover_url:
            try:
                cover_url = fetch_cover_image_url(data["title"], data["author"]) or ""
                self.stdout.write(f"  Cover: {data['title']} → {cover_url[:60]}...")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Cover fetch failed for {data['title']}: {e}"))
        book = Book.objects.create(
            title=data["title"], author=data["author"], category=data["category"],
            description=data["description"], total_chapters=len(data["chapters"]),
            pages_left=data["total_pages"], flashcards_count=len(data["flashcards"]),
            read_per_day_minutes=data.get("daily_minutes", 30),
            source=source, processing_status="completed",
            is_recommended=data.get("is_recommended", False),
            is_trending=data.get("is_trending", False),
            is_published=True,
            reading_mode=data.get("reading_mode", "deep"),
            daily_minutes=data.get("daily_minutes", 30),
            cover_image_url=cover_url,
            readers_count=data.get("readers_count", 0),
            rating=data.get("rating", 4.5),
            badge=data.get("badge", ""),
        )
        chunk_day = 1
        for ch in data["chapters"]:
            chapter = Chapter.objects.create(
                book=book, chapter_number=ch["number"], title=ch["title"],
                page_range=f"{ch['page_start']}–{ch['page_end']}",
                start_page=ch["page_start"], end_page=ch["page_end"],
                duration_in_minutes=ch.get("duration_minutes", 30),
            )
            for ck in ch["chunks"]:
                Chunk.objects.create(
                    chapter=chapter, chunk_index=ck["index"], text=ck["text"],
                    day_number=chunk_day, words_count=len(ck["text"].split()),
                    estimated_minutes=max(2, len(ck["text"].split()) // 200), is_cleaned=True,
                )
                chunk_day += 1
            Summary.objects.create(
                chapter=chapter, title=ch["summary"]["title"],
                summary_content=ch["summary"]["content"],
                key_takeaways=ch["summary"]["key_takeaways"],
            )
        for fc in data["flashcards"]:
            Flashcard.objects.create(book=book, question=fc["q"], answer=fc["a"])
        return book

    def _sched(self, user, book, ppd, progress_pct, start_date):
        """Create a ReadingSchedule with total_days/current_day derived from real chunk count."""
        from apps.books.models import ReadingSchedule
        from math import ceil
        total_chunks = sum(ch.chunks.count() for ch in book.chapters.all())
        total_days = max(1, ceil(total_chunks / ppd))
        if progress_pct >= 100:
            current_day = total_days + 1            # marks book as complete
        else:
            chunks_done = round(progress_pct / 100 * total_chunks)
            current_day = max(1, min(chunks_done // ppd + 1, total_days))
        return ReadingSchedule.objects.create(
            user=user, book=book, total_days=total_days, current_day=current_day,
            pages_per_day=ppd, start_date=start_date,
            schedule_data=[{"day": i + 1, "chunk_ids": [], "estimated_minutes": book.daily_minutes}
                           for i in range(total_days)],
        )

    def _create_admin_books(self):
        books = {}
        for key, data in [
            ("think", THINK_GROW_RICH), ("mans", MANS_SEARCH), ("happy", ART_OF_HAPPINESS),
            ("war", ART_OF_WAR), ("richest", RICHEST_MAN), ("thinketh", AS_A_MAN_THINKETH),
        ]:
            books[key] = self._make_book(data, source="admin")
        return books

    def _create_uploads(self, user):
        from apps.books.models import UserUploadedBook
        result = []
        for data in [LETTERS_STOIC, SCIENCE_RICH]:
            book = self._make_book(data, source="user_upload")
            UserUploadedBook.objects.create(
                uploaded_by=user, title=data["title"], author=data["author"],
                pdf_file="user_uploads/demo/placeholder.pdf",
                reading_mode=data.get("reading_mode", "deep"),
                daily_minutes=data.get("daily_minutes", 30),
                status="completed", book=book,
            )
            result.append(book)
        return result

    def _setup_library(self, user, admin_books):
        from apps.library.models import UserBook, ChapterProgress
        from apps.reading.models import ReadingSession
        today = date.today()
        # (key, progress_pct, days_ago)
        assignments = [
            ("think", 42, 8),
            ("war",   28, 4),
        ]
        for key, progress, days_ago in assignments:
            book = admin_books[key]
            chapters = list(book.chapters.order_by("chapter_number"))
            flat_chunks = []
            for ch in chapters:
                flat_chunks.extend(list(ch.chunks.order_by("chunk_index")))
            total_chunks = len(flat_chunks)
            chunks_done = round(progress / 100 * total_chunks)
            ub = UserBook.objects.create(
                user=user, book=book, progress_percent=progress, status="in_progress",
                is_favorite=(key == "think"),
                current_chapter=chapters[min(chunks_done // max(len(chapters), 1), len(chapters) - 1)] if chapters else None,
                current_chunk_index=chunks_done,
            )
            self._sched(user, book, 3, progress, today - timedelta(days=days_ago))
            for i, ch in enumerate(chapters):
                ch_pct = (i + 1) * (100 // len(chapters))
                completed = ch_pct <= progress
                ChapterProgress.objects.create(
                    user_book=ub, chapter=ch, is_completed=completed,
                    is_active=(not completed and i == sum(1 for j in range(len(chapters)) if (j + 1) * (100 // len(chapters)) <= progress)),
                    last_chunk_index=ch.chunks.count() if completed else 0,
                    completed_at=timezone.now() - timedelta(days=days_ago - i) if completed else None,
                )
            last_chunk = flat_chunks[min(chunks_done - 1, len(flat_chunks) - 1)] if flat_chunks and chunks_done > 0 else None
            for day_offset in range(days_ago, 0, -1):
                if day_offset % 7 == 6:
                    continue
                session_date = today - timedelta(days=day_offset)
                session = ReadingSession.objects.create(
                    user_book=ub, last_chunk=last_chunk,
                    chunks_completed=3, duration_seconds=book.daily_minutes * 60,
                )
                ReadingSession.objects.filter(id=session.id).update(
                    session_date=session_date,
                    created_at=timezone.make_aware(
                        timezone.datetime.combine(session_date, timezone.datetime.min.time())
                    ),
                )

    def _create_intelligence(self, user, all_books):
        from apps.book_intelligence.models import (
            BookIntelligenceProfile, BookIntelligenceChapter, ChapterIntelligence,
        )
        book_map = {d["title"]: d for d in [
            THINK_GROW_RICH, MANS_SEARCH, ART_OF_HAPPINESS,
            ART_OF_WAR, RICHEST_MAN, AS_A_MAN_THINKETH,
            LETTERS_STOIC, SCIENCE_RICH,
        ]}
        for book in all_books:
            data = book_map.get(book.title)
            if not data:
                continue
            profile = BookIntelligenceProfile.objects.create(
                book=book, book_type=data.get("book_type", "self_help"),
                detected_language="English",
                complexity_level=data.get("complexity_level", "intermediate"),
                status="ready", embeddings_built=True,
                book_brief=data.get("book_brief"),
                brief_generated_at=timezone.now(),
            )
            for ch_data in data["chapters"]:
                ai_ch = BookIntelligenceChapter.objects.create(
                    profile=profile, chapter_number=ch_data["number"],
                    title=ch_data["title"],
                    start_page=ch_data["page_start"], end_page=ch_data["page_end"],
                    page_range_display=f"pp. {ch_data['page_start']}–{ch_data['page_end']}",
                    chapter_hook=ch_data.get("hook", ""),
                    user_confirmed=True,
                )
                for mode in ("skim", "concept", "deep", "exam"):
                    intel = ch_data.get("intelligence", {})
                    if mode in intel:
                        ChapterIntelligence.objects.create(
                            ai_chapter=ai_ch, mode=mode, content=intel[mode],
                        )

    def _create_community(self, shahzaib, admin_books):
        from apps.community.models import Community, CommunityMember, Message, MessageReaction
        think_book = admin_books["think"]
        today = timezone.now()
        comm = Community.objects.create(
            name="Think & Grow Rich — Study Circle",
            description="Readers working through Napoleon Hill's 13 principles together. Share insights, discuss chapters, keep each other accountable.",
            community_type="book", privacy="public",
            created_by=shahzaib, book=think_book,
            cover_emoji="💰", member_count=1,
        )
        CommunityMember.objects.create(community=comm, user=shahzaib, role="admin")
        messages_data = [
            (8, "Chapter 1 just reset how I think about goals. Hill says a weak wish won't cut it — you need an obsession so intense it crowds out doubt. Starting the 6-step exercise today."),
            (7, "Auto-suggestion feels strange at first. But I've been writing my goal and reading it aloud every morning and evening. Day 4 — I already notice a mental shift."),
            (6, "The Faith chapter is wild. The idea that belief is a skill you can *manufacture* through repetition — not something you either have or don't — completely changes the equation."),
            (5, "Specialized Knowledge chapter: general education without a specific application is basically useless. You need knowledge tied to a definite purpose. Rethinking what I'm studying."),
            (4, "The Master Mind principle is so practical. It's not about finding a mentor — it's about building a small alliance of people working toward a shared goal in harmony."),
            (3, "Decision chapter is uncomfortable. Hill says successful people decide quickly and change their minds slowly. I mapped out every decision I've postponed this month. Not pretty."),
            (2, "Persistence section hit hardest. He lists 16 symptoms of lacking persistence — I had 9. The 'three feet from gold' story will stick with me forever."),
            (1, "Finished the book. The subconscious mind chapters are where it gets deep. Whether or not you buy the metaphysics, the practical technique works. On to my second read."),
        ]
        created = []
        for days_ago, text in messages_data:
            msg = Message.objects.create(community=comm, sender=shahzaib, content=text)
            Message.objects.filter(id=msg.id).update(created_at=today - timedelta(days=days_ago))
            created.append(msg)
        for msg in created[:4]:
            MessageReaction.objects.create(message=msg, user=shahzaib, emoji="🔥")
        Community.objects.filter(id=comm.id).update(member_count=1)

    def _create_qa(self, shahzaib, admin_books):
        from apps.book_intelligence.models import QAConversation, QAMessage
        try:
            profile = admin_books["think"].intelligence_profile
        except Exception:
            return
        conv = QAConversation.objects.create(user=shahzaib, profile=profile)
        pairs = [
            (
                "What is the single most important principle in Think and Grow Rich?",
                "Napoleon Hill identifies **Desire** as the cornerstone — not a mild want, but a burning obsession. Across 500 interviews, he found that the intensity of desire was the single differentiating factor between those who achieved and those who merely wished. He pairs it with Faith (manufactured through auto-suggestion) and Organized Planning to form the complete formula: know exactly what you want, believe you will achieve it, and act on a definite plan — starting now.",
            ),
            (
                "How does the subconscious mind actually work in Hill's framework?",
                "Hill describes the subconscious as an intermediary between conscious thought and what he calls Infinite Intelligence. It works 24/7, accepting any thought — positive or negative — as instruction. The practical implication: if you repeatedly feed it doubt and fear with emotional intensity, it organizes your behavior toward those outcomes. If you feed it a specific, emotionalized desire through daily written affirmations, it becomes a silent engine working toward that goal. The emotion component is critical — a mechanically repeated statement has little effect.",
            ),
            (
                "I keep losing persistence after a few weeks. What does Hill say about this?",
                "Hill identifies two root causes. First, the desire is not burning enough — a goal you'd 'like' to achieve provides no fuel when obstacles appear. Make it specific, attach a date, write it down, read it twice daily. Second, you're relying on willpower rather than habit. Willpower depletes. The solution is to make your daily action toward the goal as automatic as brushing your teeth — no decision required. He also strongly recommends a Master Mind accountability partner who will not let you quit.",
            ),
        ]
        for q, a in pairs:
            QAMessage.objects.create(conversation=conv, question=q, answer=a, source_pages=[14, 37, 52])

    def _create_notifications(self, shahzaib, all_books):
        from apps.book_intelligence.models import NotificationContent, BookIntelligenceProfile
        today = date.today()
        notif_map = {
            THINK_GROW_RICH["title"]: [
                {"morning_hook": "Your desire must be so intense it crowds out every doubt. Hill proved this studying 500 of history's most successful people.",
                 "midday_concept": "Faith is not found — it is manufactured. Repetition + genuine emotion = belief you can act on.",
                 "afternoon_story": "Edwin Barnes had no money but one unshakeable goal: to partner with Edison. He rode a freight car. He waited 5 years. He succeeded.",
                 "evening_recap": "Tonight: write your most important goal down. Be specific. Read it aloud before you sleep.", "chapter_number": 1},
                {"morning_hook": "Auto-suggestion is talking to your own subconscious with intention. Most people do it accidentally and negatively.",
                 "midday_concept": "Specialized Knowledge: useful education is tied to a purpose. General knowledge without application is inert.",
                 "afternoon_story": "Henry Ford had only an elementary education. He built the most successful industrial empire of his era by hiring people who knew what he didn't.",
                 "evening_recap": "Today's action: identify one specific skill or knowledge gap between you and your goal. Start closing it.", "chapter_number": 2},
                {"morning_hook": "Most people quit one step before success. The 'three feet from gold' principle is the most important lesson in persistence.",
                 "midday_concept": "Persistence becomes effortless when it becomes habit. The goal is to make daily action automatic, not willpower-dependent.",
                 "afternoon_story": "Darby's uncle abandoned a gold mine that turned out to be three feet from a massive vein. The junk dealer who bought his equipment became a millionaire.",
                 "evening_recap": "This evening: what have you been close to quitting? Is it really failure — or three feet from gold?", "chapter_number": 4},
            ],
            ART_OF_WAR["title"]: [
                {"morning_hook": "All warfare is based on deception. The leader who masters appearance controls the battlefield before the first move.",
                 "midday_concept": "Know your enemy and know yourself — in a hundred battles you will never be in peril. Self-knowledge is half of strategy.",
                 "afternoon_story": "Sun Tzu turned the king's concubines into soldiers. His secret: absolute clarity of command before demanding obedience.",
                 "evening_recap": "Today: identify one area of your life where you're fighting without first assessing the terrain. Map it.", "chapter_number": 1},
                {"morning_hook": "The supreme art of war is to subdue the enemy without fighting. In life: the conflict you prevent is worth more than the one you win.",
                 "midday_concept": "Speed is the essence of war — take advantage of unpreparedness, travel unexpected routes, strike where unguarded.",
                 "afternoon_story": "The general who advances without seeking fame and retreats without fearing disgrace is the real asset of the kingdom.",
                 "evening_recap": "This evening: where can you win through positioning rather than confrontation?", "chapter_number": 2},
            ],
        }
        for book in all_books:
            nd_list = notif_map.get(book.title)
            if not nd_list:
                continue
            try:
                profile = book.intelligence_profile
            except Exception:
                continue
            for i, nd in enumerate(nd_list):
                notif_date = today - timedelta(days=len(nd_list) - 1 - i)
                NotificationContent.objects.get_or_create(
                    user=shahzaib, profile=profile, date=notif_date, defaults=nd,
                )

    # ── USER 2: AROONA BIBI ──────────────────────────────────────────────────

    def _create_aroona(self):
        user = User.objects.create_user(
            email="bibiaroona1106@gmail.com",
            password="Aroona@1290",
            full_name="Aroona Bibi",
            books_read=2,
            total_pages_read=512,
            current_streak=5,
            is_avid_reader=False,
        )
        from apps.reading.models import ReadingPlan
        ReadingPlan.objects.create(user=user, pages_per_day=8, days_per_week=5, preferred_time="Morning")
        return user

    def _setup_library_aroona(self, user, admin_books, upload_books):
        from apps.library.models import UserBook, ChapterProgress
        from apps.reading.models import ReadingSession
        today = date.today()
        # Man's Search for Meaning — 100% complete (finished reader)
        mans_book = admin_books["mans"]
        mans_chapters = list(mans_book.chapters.order_by("chapter_number"))
        mans_chunks = []
        for ch in mans_chapters:
            mans_chunks.extend(list(ch.chunks.order_by("chunk_index")))
        ub_mans = UserBook.objects.create(
            user=user, book=mans_book, progress_percent=100, status="completed",
            is_favorite=True,
            current_chapter=mans_chapters[-1] if mans_chapters else None,
            current_chunk_index=len(mans_chunks),
        )
        self._sched(user, mans_book, 3, 100, today - timedelta(days=14))
        for i, ch in enumerate(mans_chapters):
            ChapterProgress.objects.create(
                user_book=ub_mans, chapter=ch, is_completed=True, is_active=False,
                last_chunk_index=ch.chunks.count(),
                completed_at=timezone.now() - timedelta(days=14 - i * 2),
            )
        for day_offset in range(14, 0, -1):
            if day_offset % 7 == 6:
                continue
            session_date = today - timedelta(days=day_offset)
            session = ReadingSession.objects.create(
                user_book=ub_mans, last_chunk=mans_chunks[-1] if mans_chunks else None,
                chunks_completed=3, duration_seconds=25 * 60,
            )
            ReadingSession.objects.filter(id=session.id).update(
                session_date=session_date,
                created_at=timezone.make_aware(
                    timezone.datetime.combine(session_date, timezone.datetime.min.time())
                ),
            )
        # Art of Happiness — 55% in progress
        happy_book = admin_books["happy"]
        happy_chapters = list(happy_book.chapters.order_by("chapter_number"))
        happy_chunks = []
        for ch in happy_chapters:
            happy_chunks.extend(list(ch.chunks.order_by("chunk_index")))
        ub_happy = UserBook.objects.create(
            user=user, book=happy_book, progress_percent=55, status="in_progress",
            is_favorite=False,
            current_chapter=happy_chapters[1] if len(happy_chapters) > 1 else happy_chapters[0],
            current_chunk_index=3,
        )
        self._sched(user, happy_book, 3, 55, today - timedelta(days=7))
        for i, ch in enumerate(happy_chapters):
            pct = (i + 1) * (100 // len(happy_chapters))
            completed = pct <= 55
            ChapterProgress.objects.create(
                user_book=ub_happy, chapter=ch, is_completed=completed, is_active=(not completed and i == 1),
                last_chunk_index=ch.chunks.count() if completed else 0,
                completed_at=timezone.now() - timedelta(days=7 - i * 2) if completed else None,
            )
        for day_offset in range(7, 0, -1):
            session_date = today - timedelta(days=day_offset)
            session = ReadingSession.objects.create(
                user_book=ub_happy,
                last_chunk=happy_chunks[min(day_offset, len(happy_chunks) - 1)] if happy_chunks else None,
                chunks_completed=3, duration_seconds=25 * 60,
            )
            ReadingSession.objects.filter(id=session.id).update(
                session_date=session_date,
                created_at=timezone.make_aware(
                    timezone.datetime.combine(session_date, timezone.datetime.min.time())
                ),
            )
        # Letters from a Stoic (upload) — added to library, not started yet
        letters_book = next((b for b in upload_books if b.title == "Letters from a Stoic"), None)
        if letters_book:
            letters_chapters = list(letters_book.chapters.order_by("chapter_number"))
            ub_letters = UserBook.objects.create(
                user=user, book=letters_book, progress_percent=0, status="not_started",
                is_favorite=False,
                current_chapter=letters_chapters[0] if letters_chapters else None,
                current_chunk_index=0,
            )
            self._sched(user, letters_book, 3, 0, today)
            for ch in letters_chapters:
                ChapterProgress.objects.create(
                    user_book=ub_letters, chapter=ch, is_completed=False, is_active=(ch == letters_chapters[0]),
                    last_chunk_index=0,
                )

    def _create_community_aroona(self, aroona, admin_books):
        from apps.community.models import Community, CommunityMember, Message, MessageReaction
        mans_book = admin_books["mans"]
        today = timezone.now()
        comm = Community.objects.create(
            name="Man's Search for Meaning — Reading Circle",
            description="A space to reflect on Frankl's lessons from the camps and how logotherapy applies to modern life. Deep discussions welcome.",
            community_type="book", privacy="public",
            created_by=aroona, book=mans_book,
            cover_emoji="🕯️", member_count=1,
        )
        CommunityMember.objects.create(community=comm, user=aroona, role="admin")
        messages_data = [
            (10, "Preface done. The fact that Frankl chose to re-enter the camps to stay with his patients rather than escape when he had the chance — I had to put the book down for a moment."),
            (8, "Part I. 'Everything can be taken from a man but one thing: the last of human freedoms — to choose one's attitude in any given set of circumstances.' Reading this at 2am. It hits differently."),
            (6, "The concept of 'provisional existence' — not knowing when it ends — is exactly how anxiety works. Frankl's insight was to treat uncertainty itself as liveable if meaning exists."),
            (4, "Part II (Logotherapy). The existential vacuum. He wrote this in 1946 and it describes social media in 2025 exactly. Boredom + meaninglessness = the real epidemic."),
            (2, "The Sunday afternoon depression he describes — I've felt that. The ache of an unscheduled day with nothing pulling you forward. Logotherapy says: find what calls you."),
            (1, "Finished. The last pages about freedom and responsibility are the best case for personal agency I've ever read. Starting Letters from a Stoic next — feels like a natural continuation."),
        ]
        created = []
        for days_ago, text in messages_data:
            msg = Message.objects.create(community=comm, sender=aroona, content=text)
            Message.objects.filter(id=msg.id).update(created_at=today - timedelta(days=days_ago))
            created.append(msg)
        for msg in created[:3]:
            MessageReaction.objects.create(message=msg, user=aroona, emoji="💡")
        Community.objects.filter(id=comm.id).update(member_count=1)

    def _create_qa_aroona(self, aroona, admin_books):
        from apps.book_intelligence.models import QAConversation, QAMessage
        try:
            profile = admin_books["mans"].intelligence_profile
        except Exception:
            return
        conv = QAConversation.objects.create(user=aroona, profile=profile)
        pairs = [
            (
                "What is logotherapy and how is it different from Freudian psychoanalysis?",
                "Logotherapy (from *logos* = meaning) is Frankl's third Viennese school of psychotherapy. Where Freud's psychoanalysis focuses on **pleasure** as the primary drive and Adler's individual psychology focuses on **power**, logotherapy identifies the will to **meaning** as the deepest human motivation.\n\nThe practical difference: Freud treats neurosis by uncovering repressed drives and resolving them. Frankl treats existential frustration (the 'noögenic neurosis') by helping the patient discover or create a specific meaning in their situation — even a situation of unavoidable suffering. Crucially, Frankl argues meaning cannot be given; it must be *found* by each person for themselves.",
            ),
            (
                "How did Frankl maintain psychological health in the camps?",
                "Frankl describes several specific mechanisms:\n\n1. **Inner life cultivation** — vividly imagining conversations with his wife, giving lectures in his mind, mentally rewriting his destroyed manuscript. The Nazis could not confiscate his inner world.\n2. **Future-orientation** — always imagining himself past the experience, as if looking back from a future vantage point. The suffering became *temporary* rather than infinite.\n3. **Meaning in suffering itself** — he concluded that even unavoidable suffering becomes bearable if it can be framed as a test of human dignity or a final act of spiritual freedom.\n4. **Humour** — brief, dark, but real. He and a fellow prisoner committed to finding one amusing thing per day, regardless of conditions.\n\nHe was careful to note this was not universally achievable — many broke, and he does not judge them.",
            ),
            (
                "What is the 'existential vacuum' and does it apply today?",
                "The existential vacuum is Frankl's term for the widespread feeling of inner emptiness that arises when traditional sources of meaning (religion, convention, instinct) no longer automatically fill the question of *how to live*.\n\nHe wrote about this in the 1950s–60s, but the description has only grown more accurate. Modern symptoms he identified:\n- **Sunday afternoon depression** — the ache of unstructured time with no clear calling\n- **Boredom as the new anxiety** — when pleasure-seeking fails to fill the void, people escalate to stimulation, aggression, or depression\n- **Collective neuroses** — conformism (doing what others do) and totalitarianism (doing what others demand) as escapes from the burden of choosing one's own meaning\n\nThe remedy is not happiness-seeking (Frankl explicitly says you cannot chase happiness directly) but **meaning-finding** — committing to something or someone beyond yourself that makes your existence feel necessary.",
            ),
        ]
        for q, a in pairs:
            QAMessage.objects.create(conversation=conv, question=q, answer=a, source_pages=[8, 47, 104])

    def _create_notifications_aroona(self, aroona, all_books):
        from apps.book_intelligence.models import NotificationContent, BookIntelligenceProfile
        today = date.today()
        notif_map = {
            MANS_SEARCH["title"]: [
                {"morning_hook": "Everything can be taken from you but one thing — your freedom to choose your response. Frankl proved this in the most extreme conditions imaginable.",
                 "midday_concept": "Logotherapy: the will to meaning is the deepest human drive — not pleasure, not power, but the need for your existence to matter.",
                 "afternoon_story": "Frankl was offered escape from the camps and turned it back. He chose to stay with his patients. That single decision became the foundation of everything he wrote.",
                 "evening_recap": "Tonight: finish this sentence — 'My existence is necessary because...' Don't stop until the answer feels true.", "chapter_number": 1},
                {"morning_hook": "The existential vacuum — the Sunday depression, the boredom beneath the scrolling — is not a mood. It's a signal that meaning is missing.",
                 "midday_concept": "Suffering ceases to be suffering when it finds a meaning. The same experience, reframed as a test of dignity, becomes survivable.",
                 "afternoon_story": "A patient came to Frankl unable to recover from his wife's death. Frankl asked: 'If you had died first, what would she have suffered?' The man saw it — he was carrying the grief *for* her. It gave the suffering meaning.",
                 "evening_recap": "What suffering in your life are you currently resisting? What meaning could it carry if you stopped fighting it?", "chapter_number": 2},
                {"morning_hook": "Don't aim at success — the more you aim at it and make it a target, the more you are going to miss it.",
                 "midday_concept": "Meaning cannot be given — it must be found. No one can tell you what your life should mean. That is both the burden and the freedom.",
                 "afternoon_story": "Frankl kept mentally rewriting his destroyed manuscript while doing forced labour. The Nazis controlled his body. His mind was writing a book that would outlive the Reich.",
                 "evening_recap": "Name one thing you are working toward that would still matter to you even if no one ever acknowledged it.", "chapter_number": 3},
            ],
            ART_OF_HAPPINESS["title"]: [
                {"morning_hook": "The very purpose of our existence is to seek happiness — but genuine happiness comes from cultivating inner peace, not accumulating pleasant circumstances.",
                 "midday_concept": "Compassion is the source of happiness — recognising that every living being wishes to avoid suffering connects you to something larger than yourself.",
                 "afternoon_story": "The Dalai Lama was asked how he maintains joy despite losing his country and watching his people suffer. His answer: 'I think of the suffering as my teacher.'",
                 "evening_recap": "Tonight: one person in your life who is suffering. What would it mean to genuinely wish for their happiness — not their gratitude, just their happiness?", "chapter_number": 1},
                {"morning_hook": "Genuine happiness is not the absence of pain — it is the presence of meaning, connection, and the ability to see beyond your own suffering.",
                 "midday_concept": "Mental immunity: the mind that has practised compassion and acceptance cannot be overwhelmed by circumstance — not because it feels less, but because it holds more.",
                 "afternoon_story": "Dr. Cutler expected the Dalai Lama to give complex spiritual answers. Instead, he gave practical psychology — modify your thinking, practise gratitude, cultivate warmth. The same advice a good therapist would give.",
                 "evening_recap": "What is one thought pattern you return to that reliably makes you feel worse? Name it specifically. Tomorrow we discuss replacing it.", "chapter_number": 2},
            ],
        }
        for book in all_books:
            nd_list = notif_map.get(book.title)
            if not nd_list:
                continue
            try:
                profile = book.intelligence_profile
            except Exception:
                continue
            for i, nd in enumerate(nd_list):
                notif_date = today - timedelta(days=len(nd_list) - 1 - i)
                NotificationContent.objects.get_or_create(
                    user=aroona, profile=profile, date=notif_date, defaults=nd,
                )

    # ── USER 3: SANA ZIA ─────────────────────────────────────────────────────

    def _create_sana(self):
        user = User.objects.create_user(
            email="szia5161@gmail.com",
            password="Sana@1290",
            full_name="Sana Zia",
            books_read=1,
            total_pages_read=265,
            current_streak=3,
            is_avid_reader=False,
        )
        from apps.reading.models import ReadingPlan
        ReadingPlan.objects.create(user=user, pages_per_day=6, days_per_week=4, preferred_time="Night")
        return user

    def _setup_library_sana(self, user, admin_books):
        from apps.library.models import UserBook, ChapterProgress
        from apps.reading.models import ReadingSession
        today = date.today()
        # The Richest Man in Babylon — 100% complete
        richest_book = admin_books["richest"]
        richest_chapters = list(richest_book.chapters.order_by("chapter_number"))
        richest_chunks = []
        for ch in richest_chapters:
            richest_chunks.extend(list(ch.chunks.order_by("chunk_index")))
        ub_richest = UserBook.objects.create(
            user=user, book=richest_book, progress_percent=100, status="completed",
            is_favorite=True,
            current_chapter=richest_chapters[-1] if richest_chapters else None,
            current_chunk_index=len(richest_chunks),
        )
        self._sched(user, richest_book, 3, 100, today - timedelta(days=12))
        for i, ch in enumerate(richest_chapters):
            ChapterProgress.objects.create(
                user_book=ub_richest, chapter=ch, is_completed=True, is_active=False,
                last_chunk_index=ch.chunks.count(),
                completed_at=timezone.now() - timedelta(days=12 - i * 3),
            )
        for day_offset in range(12, 0, -1):
            if day_offset % 7 == 6:
                continue
            session_date = today - timedelta(days=day_offset)
            session = ReadingSession.objects.create(
                user_book=ub_richest, last_chunk=richest_chunks[-1] if richest_chunks else None,
                chunks_completed=3, duration_seconds=20 * 60,
            )
            ReadingSession.objects.filter(id=session.id).update(
                session_date=session_date,
                created_at=timezone.make_aware(
                    timezone.datetime.combine(session_date, timezone.datetime.min.time())
                ),
            )
        # As a Man Thinketh — 30% in progress (just started)
        thinketh_book = admin_books["thinketh"]
        thinketh_chapters = list(thinketh_book.chapters.order_by("chapter_number"))
        thinketh_chunks = []
        for ch in thinketh_chapters:
            thinketh_chunks.extend(list(ch.chunks.order_by("chunk_index")))
        ub_thinketh = UserBook.objects.create(
            user=user, book=thinketh_book, progress_percent=30, status="in_progress",
            is_favorite=False,
            current_chapter=thinketh_chapters[0] if thinketh_chapters else None,
            current_chunk_index=2,
        )
        self._sched(user, thinketh_book, 3, 30, today - timedelta(days=3))
        for i, ch in enumerate(thinketh_chapters):
            pct = (i + 1) * (100 // len(thinketh_chapters))
            completed = pct <= 30
            ChapterProgress.objects.create(
                user_book=ub_thinketh, chapter=ch, is_completed=completed, is_active=(not completed and i == 0),
                last_chunk_index=ch.chunks.count() if completed else 2,
                completed_at=timezone.now() - timedelta(days=3) if completed else None,
            )
        for day_offset in range(3, 0, -1):
            session_date = today - timedelta(days=day_offset)
            session = ReadingSession.objects.create(
                user_book=ub_thinketh,
                last_chunk=thinketh_chunks[min(day_offset, len(thinketh_chunks) - 1)] if thinketh_chunks else None,
                chunks_completed=3, duration_seconds=20 * 60,
            )
            ReadingSession.objects.filter(id=session.id).update(
                session_date=session_date,
                created_at=timezone.make_aware(
                    timezone.datetime.combine(session_date, timezone.datetime.min.time())
                ),
            )
        # Think and Grow Rich — added to library, not started (wishlist)
        think_book = admin_books["think"]
        think_chapters = list(think_book.chapters.order_by("chapter_number"))
        ub_think = UserBook.objects.create(
            user=user, book=think_book, progress_percent=0, status="not_started",
            is_favorite=False,
            current_chapter=think_chapters[0] if think_chapters else None,
            current_chunk_index=0,
        )
        self._sched(user, think_book, 3, 0, today)
        for ch in think_chapters:
            ChapterProgress.objects.create(
                user_book=ub_think, chapter=ch, is_completed=False, is_active=(ch == think_chapters[0]),
                last_chunk_index=0,
            )

    def _create_community_sana(self, sana, admin_books):
        from apps.community.models import Community, CommunityMember, Message, MessageReaction
        richest_book = admin_books["richest"]
        today = timezone.now()
        comm = Community.objects.create(
            name="Richest Man in Babylon — Money Mindset Club",
            description="Applying the ancient laws of wealth from Clason's parables to modern financial life. Track your savings rate, share insights, stay accountable.",
            community_type="book", privacy="public",
            created_by=sana, book=richest_book,
            cover_emoji="💰", member_count=1,
        )
        CommunityMember.objects.create(community=comm, user=sana, role="admin")
        messages_data = [
            (9, "Starting this book with zero savings and three months of credit card debt. Arkad's first law: 'Pay yourself first — a portion of all you earn is yours to keep.' Setting up a 10% auto-transfer today."),
            (7, "The tale of the five laws of gold hit me hard. His son had to LOSE the gold and earn it back before he truly understood it. Clason is saying: you have to earn wisdom the same way you earn money — through experience, not just reading."),
            (5, "Seven Cures for a Lean Purse. Cure 1: save 10%. Cure 2: control expenses. Cure 3: make gold multiply. Cure 4: guard against loss. These four alone would change most people's financial lives if they actually applied them."),
            (3, "The Camel Trader of Babylon chapter. He didn't bemoan his situation — he looked at what he COULD do from where he was and did it completely. That's the whole philosophy in one parable."),
            (2, "Finished. The final chapter — 'The Luckiest Man in Babylon' — the man who was enslaved and worked his way to freedom by applying the principles. Luck is what happens when preparation meets opportunity. But you have to prepare first."),
            (1, "Week 1 result since finishing: 10% saved, first time ever. Starting As a Man Thinketh next because I want to understand the mindset layer underneath the financial habits."),
        ]
        created = []
        for days_ago, text in messages_data:
            msg = Message.objects.create(community=comm, sender=sana, content=text)
            Message.objects.filter(id=msg.id).update(created_at=today - timedelta(days=days_ago))
            created.append(msg)
        for msg in created[:3]:
            MessageReaction.objects.create(message=msg, user=sana, emoji="💎")
        Community.objects.filter(id=comm.id).update(member_count=1)

    def _create_qa_sana(self, sana, admin_books):
        from apps.book_intelligence.models import QAConversation, QAMessage
        try:
            profile = admin_books["richest"].intelligence_profile
        except Exception:
            return
        conv = QAConversation.objects.create(user=sana, profile=profile)
        pairs = [
            (
                "What is the single most important lesson from The Richest Man in Babylon?",
                "Pay yourself first — always. Before rent, before food, before any expense, set aside at least one-tenth of everything you earn as yours to keep.\n\nClason makes this point not once but through every parable: the reason most people never accumulate wealth is not low income but the habit of spending everything they earn. The merchant who earns ten coins and spends ten is no richer than the one who earns one coin — they are equally poor. The one who keeps one coin from every ten earned, and puts it to work, becomes Arkad, the richest man in Babylon.\n\nThe insight beneath the rule: most people think they cannot afford to save. Clason argues the opposite — the moment you commit to saving 10%, your expenses automatically shrink to fit the remaining 90%. The purse that is never filled forces creativity; the one that is always emptied teaches none.",
            ),
            (
                "How should I invest the savings — what do the Five Laws of Gold say?",
                "The **Five Laws of Gold** are Clason's investment framework:\n\n1. **Gold comes to those who save** — at least one-tenth, faithfully. No exceptions.\n2. **Gold multiplies for those who put it to work** — saved gold that sits idle is opportunity lost. It must work for you.\n3. **Gold clings to the owner who invests with wise counsel** — seek advice only from those who are expert in their field. A jeweller's advice on land is worth nothing.\n4. **Gold slips away from those who invest in businesses they don't understand** — Rodan lost his gold to the shield-maker's merchant brother because he invested in something unfamiliar under emotional pressure.\n5. **Gold flees from those who would force it to impossible earnings** — if an investment promises unusually high returns, it is usually because the risk is unusually high. Guard against loss first; growth second.\n\nThe hierarchy: earn → save 10% → multiply conservatively → guard against loss → seek expert counsel only.",
            ),
            (
                "I keep spending my full income every month. How do I actually start?",
                "Clason's answer through Arkad: **start with one-tenth, automatically, before you see it.** The mechanism matters more than the motivation.\n\nPractical translation:\n1. On payday, move 10% to a separate account *first* — before paying anything else. Make it automatic so no decision is required.\n2. Do not adjust your lifestyle to feel the loss — within 2–3 months, your expenses will compress to fit the remaining 90% without you noticing.\n3. The psychological shift: when your savings account grows for the first time, the feeling of watching your wealth increase becomes its own motivation. The habit feeds itself.\n\nArkad also says: do not torture yourself over the 90% you spend — spend it freely and without guilt. The discipline is in the 10%, not in self-denial of everything. This makes it sustainable.\n\nHis final word on starting: 'A part of all I earn is mine to keep.' Say it until it is true.",
            ),
        ]
        for q, a in pairs:
            QAMessage.objects.create(conversation=conv, question=q, answer=a, source_pages=[22, 55, 89])

    def _create_notifications_sana(self, sana, all_books):
        from apps.book_intelligence.models import NotificationContent, BookIntelligenceProfile
        today = date.today()
        notif_map = {
            RICHEST_MAN["title"]: [
                {"morning_hook": "'A part of all I earn is mine to keep.' Say it until it is true. Arkad built Babylon's greatest fortune from this one sentence.",
                 "midday_concept": "The Five Laws of Gold: earn, save 10%, multiply wisely, guard against loss, seek expert counsel only. Each law compounds the one before it.",
                 "afternoon_story": "Arkad's classmates thought his wealth was luck. He invited them to dinner and showed them his clay tablets — decade after decade of consistent saving and compounding. Luck had nothing to do with it.",
                 "evening_recap": "Check your spending from this week. How much of what you earned is still yours? Set up the 10% auto-transfer if you haven't.", "chapter_number": 1},
                {"morning_hook": "The Camel Trader did not ask 'why me?' He asked 'what can I do from here?' That question is the whole philosophy in four words.",
                 "midday_concept": "Guard against loss before seeking gain. Most wealth is destroyed not by bad investments but by not protecting what was already built.",
                 "afternoon_story": "Rodan the spear-maker received 50 pieces of gold and was immediately pressured by his sister's husband to invest it. Mathon the money-lender taught him: desire for quick gain is the fastest road back to poverty.",
                 "evening_recap": "What is one financial decision you're being pressured into right now? Does the person advising you have expertise in that specific area?", "chapter_number": 2},
            ],
            AS_A_MAN_THINKETH["title"]: [
                {"morning_hook": "As a man thinketh in his heart, so is he. Not occasionally. Not in his best moments. Always and completely.",
                 "midday_concept": "Thought is the cause; circumstance is the effect. Until you believe this completely, you will keep looking for external solutions to internal problems.",
                 "afternoon_story": "Allen himself was penniless and obscure when he wrote this. He wrote it as a discovery, not a theory — these were lessons he had to learn through failure before he could teach them.",
                 "evening_recap": "What thought do you return to most often? Does it describe who you want to become — or explain why you can't?", "chapter_number": 1},
            ],
        }
        for book in all_books:
            nd_list = notif_map.get(book.title)
            if not nd_list:
                continue
            try:
                profile = book.intelligence_profile
            except Exception:
                continue
            for i, nd in enumerate(nd_list):
                notif_date = today - timedelta(days=len(nd_list) - 1 - i)
                NotificationContent.objects.get_or_create(
                    user=sana, profile=profile, date=notif_date, defaults=nd,
                )


# ─────────────────────────────────────────────────────────────────────────────
# BOOK DATA
# ─────────────────────────────────────────────────────────────────────────────

THINK_GROW_RICH.update({
    "title": "Think and Grow Rich",
    "author": "Napoleon Hill",
    "category": "Self-Help",
    "total_pages": 238,
    "readers_count": 15_000_000,
    "rating": 4.7,
    "cover_image_url": "https://m.media-amazon.com/images/I/61y04HNWmzL._AC_UY218_.jpg",
    "is_recommended": True, "is_trending": False,
    "reading_mode": "deep", "daily_minutes": 30,
    "book_type": "self_help", "complexity_level": "beginner", "badge": "CLASSIC",
    "description": (
        "After twenty years interviewing over five hundred of history's most successful people — "
        "including Andrew Carnegie, Henry Ford, and Thomas Edison — Napoleon Hill distilled their secrets "
        "into thirteen timeless principles. First published in 1937, this is the book that has quietly "
        "sat on the shelf of nearly every self-made achiever since. It is not about money alone — "
        "it is a complete philosophy of achievement applicable to any goal."
    ),
    "book_brief": {
        "what": "A 13-principle philosophy of achievement derived from 20 years of studying 500+ successful people.",
        "who": "Anyone who wants to transform a specific desire into tangible achievement, regardless of background, education, or resources.",
        "core_argument": "All achievement begins as a state of mind. A burning, specific desire combined with faith, organized planning, and persistence will manifest any definite goal.",
        "top_5_ideas": [
            "Burning Desire: Your goal must be an obsession, not a wish. Intensity and clarity are non-negotiable.",
            "Manufactured Faith: Belief is a skill built through daily emotionalized repetition — not a trait you either have or don't.",
            "Specialized Knowledge: Learning tied to a definite purpose beats general education every time.",
            "Master Mind Alliance: Two or more harmonious minds create combined intelligence greater than the sum of its parts.",
            "Persistence as Habit: Willpower depletes; habit does not. Make daily action toward your goal as automatic as brushing your teeth.",
        ],
        "verdict": "Timeless, foundational, and deceptively practical. Apply the six-step desire formula from Day 1.",
    },
    "flashcards": [
        {"q": "What are Hill's Six Steps for turning desire into achievement?", "a": "1) Fix exact goal; 2) Define what you'll give; 3) Set a deadline; 4) Create a plan and start now; 5) Write it all down; 6) Read it aloud twice daily with conviction."},
        {"q": "Why must desire be 'burning' rather than just strong?", "a": "Only obsessive desire crowds out doubt, keeps you alert to disguised opportunity, and sustains the persistence needed to survive temporary defeat."},
        {"q": "What is auto-suggestion and why does emotion matter?", "a": "Auto-suggestion is deliberate, repeated instruction to the subconscious. Emotion is the carrier wave — without it, repetition has little effect. With it, the subconscious accepts the goal as instruction."},
        {"q": "What is the Master Mind principle?", "a": "An alliance of 2+ people working in perfect harmony toward a shared definite purpose, creating combined intelligence greater than any single mind."},
        {"q": "What does 'three feet from gold' mean?", "a": "Most people quit one step before success. Darby's uncle abandoned a gold mine three feet from a massive vein — the junk dealer who bought his drill became wealthy."},
        {"q": "What are Hill's six major fears?", "a": "Poverty (most destructive), criticism, ill health, loss of love, old age, and death. Fear of poverty is worst because it paralyzes action while masquerading as caution."},
    ],
    "chapters": [
        {
            "number": 1, "title": "Desire — The Starting Point of All Achievement",
            "page_start": 1, "page_end": 38, "duration_minutes": 45,
            "hook": "Every great achievement began as a thought fired by one thing: an all-consuming desire that refused to accept any outcome but success.",
            "chunks": [
                {"index": 1, "day": 1, "text": (
                    "Napoleon Hill opens with a story designed to permanently change how you think about failure. "
                    "Edwin C. Barnes arrived at Thomas Edison's laboratory with nothing — no money, no connections, no credentials. "
                    "He couldn't afford a train ticket and rode a freight car instead. What he carried was invisible: a desire so consuming "
                    "it left no room for doubt.\n\n"
                    "Barnes didn't want to work *for* Edison. He wanted to work *with* him as a business partner. Most people set goals "
                    "calibrated by their current circumstances. Barnes decided what he wanted first, then organized his entire life around it — "
                    "without asking permission from reality.\n\n"
                    "Edison sensed something immediately — not experience, but the fire of absolute conviction. Barnes was given a minor role. "
                    "Five years passed. He didn't waver. When Edison's salesmen dismissed the Ediphone dictating machine as unsellable, "
                    "Barnes seized the opening and built a sales empire around it. His desire had kept him ready for the moment others missed.\n\n"
                    "Hill's lesson is precise: opportunity usually arrives disguised as misfortune or temporary defeat. "
                    "Burning desire is what allows you to recognize it when it does."
                )},
                {"index": 2, "day": 2, "text": (
                    "Hill draws a sharp line between *wishing* for something and *desiring* it — and the difference is the entire book.\n\n"
                    "Wishing is passive. It asks the world to deliver something while you wait comfortably. Desire, in Hill's framework, "
                    "is an active psychological force — an obsession that reshapes daily habits, dominates thinking, and refuses any outcome but success.\n\n"
                    "He presents one of the most powerful parables in the book: a general who lands his forces on enemy shores and burns his own ships. "
                    "With no retreat possible, there is only one direction — forward. The soldiers fight with ferocity born not of courage "
                    "alone but of necessity. Hill argues every person who achieves great things makes this same psychological move: "
                    "committing so completely that retreat becomes unthinkable.\n\n"
                    "He then presents the famous **Six Steps** for crystallising desire:\n\n"
                    "1. Fix the exact amount you desire — not 'a lot' but a specific number.\n"
                    "2. Determine what you will give in exchange.\n"
                    "3. Establish a definite date.\n"
                    "4. Create a plan — begin at once, whether ready or not.\n"
                    "5. Write it all down in a clear statement.\n"
                    "6. Read it aloud twice daily — before sleeping and upon waking — seeing and feeling yourself already in possession of the goal."
                )},
                {"index": 3, "day": 3, "text": (
                    "Hill closes the Desire chapter with his most personal story — one he admits was difficult to include.\n\n"
                    "His son, Blair Hill, was born without ears and was medically classified as deaf. Rather than accept this verdict, "
                    "Hill decided to instill in Blair an unshakeable desire to hear and speak normally. From infancy, he repeated one message: "
                    "your situation is not permanent. Blair absorbed this conviction so completely he refused to learn sign language — "
                    "doing so would have meant accepting the limitation.\n\n"
                    "By early adulthood, Blair could hear nearly as well as a hearing person using a specialized amplifier. "
                    "More remarkably, he contacted the manufacturer and connected thousands of other deaf people with the same technology. "
                    "One burning desire — implanted by a father who refused to accept circumstances as final — rippled out and changed thousands of lives.\n\n"
                    "Hill's conclusion is both philosophical and practical: the mind does not recognise the boundary between "
                    "what is merely unconventional and what is impossible. It simply follows instruction. "
                    "When that instruction is fired by desire and consistently reinforced, it organises the world around the goal "
                    "in ways that appear, from the outside, almost miraculous."
                )},
            ],
            "summary": {"title": "Desire: The Engine of Every Achievement",
                "content": "Chapter 1 establishes the cornerstone of Hill's philosophy: burning, obsessive desire — not mild wishing — is the starting point of all achievement. Through the stories of Edwin Barnes, a general burning his ships, and Hill's deaf son Blair, the chapter proves that intensity of desire organises circumstances and people in service of the goal. The Six Steps form the first practical tool of the book.",
                "key_takeaways": ["Desire must be specific, intense, and obsessive — not a vague wish.", "Burning your boats — eliminating retreat — creates the focus needed for achievement.", "The Six Steps convert abstract desire into a written, daily-reviewed action plan.", "Opportunity arrives disguised as temporary defeat; only burning desire keeps you alert to it."]},
            "intelligence": {
                "skim": {"one_liner": "Burning, specific desire — not wishing — is the single starting point of every achievement; the Six Steps convert that desire into a written, twice-daily action plan."},
                "concept": {"concepts": [
                    {"name": "Burning Desire", "description": "An obsessive, all-consuming focus on a specific goal that crowds out doubt. Distinguished from wishing by intensity, clarity, and refusal to accept defeat."},
                    {"name": "The Six Steps", "description": "Fix exact goal → define the trade → set a date → create a plan and start now → write it down → read aloud twice daily with genuine emotion."},
                    {"name": "Burning the Boats", "description": "Psychological commitment so total that retreat becomes impossible — the mental equivalent of a general destroying his own ships to force his army to fight forward."},
                ]},
                "deep": {
                    "breakdown": "Hill's desire framework operates on a precise psychological mechanism: the subconscious cannot distinguish between a vividly imagined reality and physical experience. By writing a goal with specificity, attaching a date, and reading it with genuine emotion twice daily, you repeatedly programme the subconscious with a clear instruction. The subconscious then adjusts behavior, filters perception, and draws in resources aligned with that goal — what neuroscience now calls the Reticular Activating System (RAS).",
                    "examples": ["Edwin Barnes: desired to partner with Edison, rode freight trains, waited 5 years, seized his moment.", "Blair Hill: born deaf, given desire for normal hearing by his father, achieved functional hearing and helped thousands.", "The general burning his ships: psychological commitment that made victory the only option."],
                    "analogy": "Desire is like a magnifying glass. Scattered light (vague wanting) produces only warmth. Focused, intense light (burning desire) starts a fire.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What are Hill's Six Steps?", "answer": "Fix exact goal; define what you'll give; set a date; create a plan and start now; write it down; read aloud twice daily with emotion."},
                    {"question": "Why does Hill insist on 'burning' desire vs strong desire?", "answer": "Only obsessive desire crowds out doubt, sustains persistence through defeat, and keeps you alert to disguised opportunities."},
                    {"question": "What lesson does Edwin Barnes illustrate?", "answer": "That burning desire — not resources or connections — is the starting currency of success. He partnered with Edison having nothing but absolute conviction."},
                ]},
            },
        },
        {
            "number": 2, "title": "Faith — Visualizing and Believing in Attainment",
            "page_start": 39, "page_end": 72, "duration_minutes": 40,
            "hook": "Faith is not a gift handed to the lucky — it is a skill anyone can build through deliberate, emotionalized practice.",
            "chunks": [
                {"index": 4, "day": 4, "text": (
                    "Hill's declaration at the start of this chapter challenges most people's assumptions: "
                    "**faith is not found — it is manufactured**. You don't wait for belief to arrive. You create it deliberately.\n\n"
                    "The technique is called *auto-suggestion* — the systematic repetition of a specific, emotionalized goal statement. "
                    "Twice daily, you read your written goal aloud with genuine conviction. The emotion is not optional. "
                    "A statement repeated mechanically has almost no effect. The same statement delivered with feeling begins rewiring the mind.\n\n"
                    "Hill explains this through a broadcasting analogy: the subconscious operates on specific emotional frequencies. "
                    "Thought alone is a signal too weak to reach its destination. Emotion amplifies the signal until it penetrates "
                    "the subconscious and takes root. Once the subconscious receives a clear, emotionalized instruction, "
                    "it begins working — silently, continuously — to organize behavior and perception toward that goal.\n\n"
                    "The radical implication: the person who says 'I can't believe in myself because I've failed too many times' "
                    "simply doesn't know that belief is a buildable skill — one that responds to the same consistent practice "
                    "that develops any other competency."
                )},
                {"index": 5, "day": 5, "text": (
                    "Hill turns to the six major fears that poison faith — the most prevalent psychological obstacles to achievement he found across 500 subjects:\n\n"
                    "**Fear of poverty** — the most destructive of all. It paralyses action and convinces the mind that caution is wisdom. "
                    "The person afraid of poverty unconsciously sabotages every opportunity that carries risk — which is every real opportunity.\n\n"
                    "**Fear of criticism** — responsible for killing more ambitions than any other force. It creates the devastating habit "
                    "of conformity: doing what others expect instead of what the self knows is right. Most dreams die here.\n\n"
                    "**Fear of ill health** — often self-fulfilling through chronic worry and hypochondria.\n\n"
                    "**Fear of loss of love** — creates jealousy and control that destroys what it fears losing.\n\n"
                    "**Fear of old age** — produces premature decline by convincing the mind that capacity is shrinking.\n\n"
                    "**Fear of death** — wastes the present by dwelling on an inevitable future.\n\n"
                    "The antidote in every case is identical: replace the fear-thought immediately with its positive counterpart, "
                    "delivered with equal emotional force. This is not 'positive thinking' as casual optimism — "
                    "it is deliberate psychological reprogramming applied with the same precision as auto-suggestion."
                )},
                {"index": 6, "day": 6, "text": (
                    "The most provocative passage in the Faith chapter is Hill's claim that the subconscious, operating under "
                    "intense emotion and desire, can connect with what he calls **Infinite Intelligence** — "
                    "a universal source from which all creativity and genuine insight draw.\n\n"
                    "Whether or not you accept this metaphysical framing, the practical framework Hill derives from it is concrete. "
                    "He points to the near-universal experience among great achievers of sudden, unexpected insight — "
                    "the solution that arrives in the middle of the night, the answer that surfaces during a walk "
                    "after days of frustrated effort. Modern neuroscience describes this as the default mode network "
                    "processing problems below conscious awareness. Hill calls it the subconscious doing its deepest work.\n\n"
                    "The practical method: **before sleeping, place a specific problem or question in your subconscious "
                    "by writing it down clearly and emotionalizing it.** Don't force a solution. Relax, release the question, "
                    "and record whatever arrives on waking — in a notebook kept beside the bed.\n\n"
                    "Carnegie, Ford, and Edison all used variations of this practice. Ford was famous for entering "
                    "what his staff called 'the brown study' — a state of deep, unfocused relaxation from which "
                    "his most elegant engineering solutions consistently emerged."
                )},
            ],
            "summary": {"title": "Faith: Manufacturing Belief Through Deliberate Practice",
                "content": "Faith is a manufactured state of mind, not a passive gift. Through auto-suggestion, the systematic emotionalized repetition of a specific goal, anyone can build belief from scratch. Hill identifies the six fears that destroy faith and provides a practical method for using the subconscious during sleep as a problem-solving tool.",
                "key_takeaways": ["Faith is manufactured through repetition + emotion — not discovered by luck.", "Negative self-talk programmes the subconscious just as powerfully as affirmations.", "The six fears (poverty, criticism, ill health, lost love, old age, death) are the primary destroyers of belief.", "Plant a specific question before sleeping; record what arrives on waking."]},
            "intelligence": {
                "skim": {"one_liner": "Faith is a manufactured skill — created through emotionalized daily repetition of your goal — not a trait you either have or don't."},
                "concept": {"concepts": [
                    {"name": "Auto-Suggestion", "description": "Systematic, emotionalized, twice-daily repetition of a specific goal statement that programmes the subconscious to work toward that goal."},
                    {"name": "Six Major Fears", "description": "Poverty, criticism, ill health, loss of love, old age, death — the primary thought patterns that poison faith and paralyse decisive action."},
                    {"name": "Subconscious Problem-Solving", "description": "Placing a specific question in the subconscious before sleep, then recording insights on waking — a technique used by Edison, Ford, and Carnegie."},
                ]},
                "deep": {
                    "breakdown": "Hill's faith framework is essentially applied cognitive-behavioural reprogramming from 1937. The act of writing goals, attaching emotion, and repeating them daily is neurologically equivalent to what modern CBT calls cognitive restructuring. The emotion requirement aligns with current understanding of the amygdala's role in memory consolidation — emotionally charged content is encoded more deeply and durably than neutral content.",
                    "examples": ["Barnes maintained faith for 5 years in a junior role before his opportunity appeared.", "Blair Hill refused sign language — faith installed by his father made the limitation non-final."],
                    "analogy": "Auto-suggestion is like a drip-irrigation system for the mind. Your goal is the seed. Without consistent water (emotionalized repetition), it never germinates. With it, even difficult goals take root.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is auto-suggestion and why is emotion essential?", "answer": "Auto-suggestion is the deliberate, repeated delivery of an emotionalized goal statement to the subconscious. Emotion is the carrier wave — without it, repetition has little effect. With it, the subconscious accepts the goal as instruction."},
                    {"question": "List Hill's six major fears, identifying the most destructive.", "answer": "Poverty (most destructive — paralyses action while masquerading as caution), criticism, ill health, loss of love, old age, death."},
                ]},
            },
        },
        {
            "number": 3, "title": "Organized Planning — Crystallizing Desire into Action",
            "page_start": 73, "page_end": 140, "duration_minutes": 50,
            "hook": "Desire is the fuel. Faith is the engine. Organized planning is the vehicle that actually moves you forward.",
            "chunks": [
                {"index": 7, "day": 7, "text": (
                    "By Chapter 6, Hill has established desire and faith. Now comes the vehicle: an organized plan.\n\n"
                    "He punctures a common myth immediately: great achievers didn't succeed through individual genius. "
                    "Every major fortune was built through a harmonious alliance of minds — what Hill calls the **Master Mind**. "
                    "Carnegie's steel empire was built on the coordinated effort of over fifty men. Ford's revolution required thousands "
                    "of specialists, each contributing their piece to a vision one man held with absolute clarity.\n\n"
                    "Hill's instruction is direct: **form your own Master Mind alliance now.** Not abstractly — "
                    "a specific group of two to seven people, chosen for knowledge and ability complementary to yours, "
                    "meeting regularly with a definite shared purpose. The group must operate in harmony; "
                    "a single member driven by jealousy or self-interest poisons the entire alliance.\n\n"
                    "What makes the Master Mind more than mere collaboration? Hill's claim — observed across 500 subjects — "
                    "is that when minds work in perfect coordination, a third intelligence emerges greater than the sum of its parts. "
                    "Whether explained as synergy, idea cross-pollination, or something more fundamental, the effect is consistently reproducible."
                )},
                {"index": 8, "day": 8, "text": (
                    "Hill turns to what most people find the hardest topic in any achievement philosophy: **what to do when the plan fails.**\n\n"
                    "Most people treat a failed plan as a failed self. Hill calls this a cognitive error with catastrophic consequences. "
                    "A plan is a hypothesis, not an identity. When it fails, the correct response is not despair but immediate replacement: "
                    "devise a new plan, consult your Master Mind, resume. The desire does not change. The plan — a mere tool — is updated.\n\n"
                    "He introduces the concept of **temporary defeat** versus permanent failure. Permanent failure is a conscious choice: "
                    "the decision to stop trying. Every other setback is temporary defeat — and temporary defeat carries, as a near-universal law, "
                    "**the seed of an equivalent or greater benefit.** The challenge is that this seed is invisible in the moment of defeat. "
                    "Only those with burning desire stay present long enough to harvest it.\n\n"
                    "His evidence: every one of the 500 wealthy Americans he studied had experienced what they described as their greatest failure. "
                    "In every single case, that failure was later identified as the turning point that made the ultimate success possible. "
                    "Without the failure, the path to the greater achievement would never have been revealed."
                )},
                {"index": 9, "day": 9, "text": (
                    "The final section of Organized Planning contains what many readers consider the most practically valuable pages in the entire book: "
                    "Hill's catalogue of the **qualities of leadership** and the thirty major causes of failure.\n\n"
                    "The qualities he identifies as essential for leadership appear again and again across every great figure in history:\n\n"
                    "**Unwavering courage** — not recklessness, but action despite fear, grounded in knowledge of one's own ability.\n"
                    "**Self-control** — the person who cannot control themselves cannot lead others.\n"
                    "**Definiteness of decision** — great leaders decide quickly and change their minds slowly. Followers do the reverse.\n"
                    "**The habit of doing more than paid for** — the surest path to advancement in any organisation.\n"
                    "**A pleasing personality** — not superficial charm but genuine, cooperative warmth that earns lasting loyalty.\n\n"
                    "Against these, Hill lists the most common causes of failure: lack of a definite purpose, lack of ambition, "
                    "insufficient self-discipline, procrastination (which he calls *the most prevalent single cause of failure*), "
                    "and the habit of giving up at the first sign of defeat.\n\n"
                    "Reading this list as a self-diagnostic — not a judgment — is one of the most useful exercises in the book."
                )},
            ],
            "summary": {"title": "Organized Planning: Building the Structure That Turns Desire Into Reality",
                "content": "No desire becomes reality without an organized plan. Hill introduces the Master Mind alliance as the structural foundation of all great achievement, teaches that failed plans are hypotheses to be replaced — not evidence of personal failure — and provides a leadership and failure-cause framework for rigorous self-assessment.",
                "key_takeaways": ["No major achievement is built alone — form your Master Mind alliance immediately.", "A failed plan is a failed hypothesis, not a failed self. Replace the plan; maintain the desire.", "Temporary defeat always contains the seed of an equivalent benefit — persistence is what reveals it.", "Procrastination is the most common single cause of failure."]},
            "intelligence": {
                "skim": {"one_liner": "Build a Master Mind, replace failed plans relentlessly, and treat every setback as temporary — the seed of an equivalent benefit always lies within."},
                "concept": {"concepts": [
                    {"name": "Master Mind Alliance", "description": "2–7 people in perfect harmony working toward a shared definite purpose, creating combined intelligence greater than any individual member."},
                    {"name": "Temporary Defeat vs Failure", "description": "Failure is the choice to stop. Every other setback is temporary, containing the seed of an equivalent or greater benefit for those who persist."},
                    {"name": "Leadership Qualities", "description": "Courage, self-control, justice, decisiveness, definite plans, and doing more than expected — the universal profile of successful leaders across every field."},
                ]},
                "deep": {
                    "breakdown": "Hill's planning chapter is really about resilience architecture — building structural and psychological systems that allow you to absorb failure without being defined by it. The Master Mind provides external accountability and cross-pollination. The 'seed of equivalent benefit' reframe prevents catastrophizing. Together they create a system where failure becomes data rather than verdict.",
                    "examples": ["Carnegie coordinated 50 men to build his steel empire.", "Ford required thousands of specialists contributing pieces to his singular vision."],
                    "analogy": "A plan is a map, not a contract. When the road washes out, you find another route. You don't abandon the destination.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is the Master Mind and why must it operate in harmony?", "answer": "2–7 people working toward a shared purpose in perfect harmony, creating combined intelligence greater than the sum of its parts. A single member with conflicting motives destroys the synergistic effect."},
                    {"question": "How does Hill distinguish temporary defeat from permanent failure?", "answer": "Permanent failure is a conscious choice to stop trying. Temporary defeat is any setback that hasn't been met with that choice — and every temporary defeat carries the seed of an equivalent benefit."},
                ]},
            },
        },
        {
            "number": 4, "title": "Persistence — The Sustained Effort That Transforms Desire Into Reality",
            "page_start": 141, "page_end": 185, "duration_minutes": 45,
            "hook": "Persistence is to character what carbon is to steel — the element that transforms ordinary metal into something unbreakable.",
            "chunks": [
                {"index": 10, "day": 10, "text": (
                    "Hill opens the Persistence chapter with a statement that stops most readers: "
                    "*'There is no substitute for persistence. The person who makes persistence their watchword discovers that Old Man Failure eventually becomes tired and makes his departure.'*\n\n"
                    "He then delivers what many consider the most important insight in the book: **most people quit one step before success.**\n\n"
                    "R.U. Darby's uncle went west during the gold rush and staked a claim that produced rich gold ore. He drilled for a time, "
                    "found a strong vein — then it disappeared. He quit in disgust, sold his equipment to a junk dealer for a few hundred dollars, "
                    "and returned home defeated.\n\n"
                    "The junk dealer brought in a mining engineer who surveyed the site and concluded the vein hadn't disappeared — "
                    "it had simply shifted three feet to the left. He resumed drilling, found the vein within three feet, "
                    "and extracted millions from the same mine Darby's uncle had abandoned.\n\n"
                    "Darby went on to become one of the most successful life insurance salespeople in America. "
                    "He later said the lesson of 'three feet from gold' was the invisible force behind every sale he refused to abandon "
                    "— every no that he treated not as rejection but as three feet from yes."
                )},
                {"index": 11, "day": 11, "text": (
                    "Hill gives persistence practical structure through **four essential components** that, working together, "
                    "make sustained effort possible even under sustained adversity:\n\n"
                    "**1. A definite purpose backed by burning desire.** Without a specific goal you want badly enough, "
                    "there is no fuel. Vague goals produce vague effort that evaporates at the first obstacle.\n\n"
                    "**2. A definite plan expressed in continuous action.** Persistence is not passive waiting — it is doing something "
                    "every single day, however small, that moves you toward the goal.\n\n"
                    "**3. A mind closed tightly against all negative and discouraging influences.** This includes well-meaning people "
                    "who advise caution. Their concern feels like wisdom; their doubt feels like realism. Both are poison.\n\n"
                    "**4. A friendly alliance with people who will encourage you to follow through.** The Master Mind operating "
                    "not just as an intellectual resource but as an emotional accountability structure.\n\n"
                    "He then lists the sixteen symptoms of lacking persistence — a self-diagnostic that most readers find uncomfortable "
                    "because so many items apply: *failure to recognise opportunity*, *the habit of quitting at the first sign of defeat*, "
                    "*wishing instead of willing*, and *the tendency to compromise rather than meet obstacles head-on.*"
                )},
                {"index": 12, "day": 12, "text": (
                    "The final insight of the Persistence chapter is the most counterintuitive in Hill's entire framework: "
                    "**willpower alone cannot sustain persistence.** Willpower is a depleting resource. The person who relies on it "
                    "to maintain effort will fail as surely as the person who relies on motivation.\n\n"
                    "What sustains genuine persistence is the *habitualisation* of effort — making daily action toward your goal "
                    "as automatic and unremarkable as brushing your teeth. You don't summon willpower to do that; it simply happens. "
                    "When effort toward your goal reaches that level of automaticity, the obstacles that would stop a willpower-dependent "
                    "person become invisible to you.\n\n"
                    "Hill's technique for building this habit: begin each day by reviewing your written goal statement before you've "
                    "fully woken. The half-awake mind is most receptive to the subconscious and least armoured with the day's doubts. "
                    "Five minutes of focused, emotionalized review at this moment is worth an hour of afternoon effort.\n\n"
                    "His closing challenge: pick your single most important goal, apply the Six Steps, form your Master Mind, "
                    "begin your plan today, and persist without exception for ninety days. Do this honestly, and you will not need "
                    "to be convinced of these principles — you will have proved them to yourself."
                )},
            ],
            "summary": {"title": "Persistence: The Final Barrier Between Desire and Achievement",
                "content": "Most people quit one step before success. The 'three feet from gold' story illustrates this with devastating clarity. Hill provides the four components of persistence, explains why willpower is insufficient, and offers the habit-formation technique that makes sustained effort possible over months and years rather than just days.",
                "key_takeaways": ["Most people quit one step before success — three feet from gold.", "Persistence requires: burning desire, daily action, a closed mind against discouragement, and an accountability alliance.", "Willpower depletes; habit doesn't. Make daily effort toward your goal automatic.", "Review your written goal in the half-awake morning state — the subconscious is most receptive then."]},
            "intelligence": {
                "skim": {"one_liner": "Most people quit one step before success; persistence through habit (not willpower), a closed mind against discouragement, and a Master Mind accountability group is the final differentiator."},
                "concept": {"concepts": [
                    {"name": "Three Feet from Gold", "description": "Darby's uncle quit mining three feet from a massive vein — illustrating that the moment of greatest temptation to quit is often closest to success."},
                    {"name": "Four Components of Persistence", "description": "Definite purpose + burning desire; daily action on a definite plan; closed mind against discouragement; accountability alliance with encouraging partners."},
                    {"name": "Habit vs Willpower", "description": "Willpower is finite and depletes under sustained pressure. True persistence comes from making daily effort toward your goal automatic — below the level of conscious decision."},
                ]},
                "deep": {
                    "breakdown": "Hill's persistence framework anticipates modern behavioral science by decades. His distinction between willpower and habit maps onto what psychologists now call 'ego depletion' — self-control draws from a limited resource that fatigues. The solution — habitualisation — aligns with BJ Fogg's 'Tiny Habits' research: anchor a small action to an existing cue, repeat until automatic, then scale.",
                    "examples": ["Darby's uncle: quit 3 feet from gold — the mine that made the junk dealer a millionaire.", "Barnes: maintained effort for 5 years in a junior role before the partnership opportunity appeared."],
                    "analogy": "Persistence is like water wearing stone. No single drop matters. But uninterrupted flow, applied consistently to one point, eventually cuts through anything.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What are the four components of persistence?", "answer": "1) Definite purpose backed by burning desire; 2) definite plan + daily action; 3) closed mind against negative influences; 4) accountability alliance with encouraging partners."},
                    {"question": "Why is willpower insufficient for sustained persistence?", "answer": "Willpower is a depleting resource that fatigues under sustained pressure. True persistence requires habitualising daily effort until it requires no conscious decision — as automatic as brushing your teeth."},
                ]},
            },
        },
    ],
})

# ─── THE ART OF WAR ───────────────────────────────────────────────────────────
ART_OF_WAR.update({
    "title": "The Art of War",
    "author": "Sun Tzu",
    "category": "Strategy & Leadership",
    "total_pages": 96,
    "readers_count": 8_000_000,
    "rating": 4.6,
    "cover_image_url": "https://m.media-amazon.com/images/I/71EQ7pinRdL._AC_UY218_.jpg",
    "is_recommended": False, "is_trending": True,
    "reading_mode": "concept", "daily_minutes": 20,
    "book_type": "strategy", "complexity_level": "intermediate", "badge": "TIMELESS",
    "description": "Written over 2,500 years ago, The Art of War remains the most influential strategic treatise ever written. Thirteen concise chapters cover planning, deception, positioning, and leadership — principles applied today by military commanders, CEOs, and negotiators worldwide.",
    "book_brief": {
        "what": "A 2,500-year-old strategic masterpiece in 13 chapters covering warfare, leadership, and competitive positioning.",
        "who": "Anyone navigating competition — in business, negotiation, sport, or life — who wants a framework for winning with minimum waste.",
        "core_argument": "Victory belongs to the strategist who wins before the battle begins — through superior planning, deception, and self-knowledge.",
        "top_5_ideas": [
            "All warfare is based on deception — appear unlike reality to control the enemy's response.",
            "Know yourself and your enemy — in a hundred battles you will never be in peril.",
            "The supreme art is to subdue the enemy without fighting.",
            "Invincibility lies in defence; the possibility of victory lies in attack.",
            "Adapt like water — permanent principles, perpetually fresh application.",
        ],
        "verdict": "Read slowly. Each aphorism contains more strategy than most modern business books combined.",
    },
    "flashcards": [
        {"q": "What is Sun Tzu's most famous strategic principle?", "a": "Know yourself and know your enemy — in a hundred battles you will never be in peril."},
        {"q": "What is the supreme art of war?", "a": "To subdue the enemy without fighting — winning through positioning and intelligence before the first blow."},
        {"q": "What are the five fundamental strategic factors?", "a": "Moral Law (alignment), Heaven (timing), Earth (terrain), the Commander (leadership), Method (discipline)."},
        {"q": "What does 'all warfare is based on deception' mean in practice?", "a": "Appear weak when strong, strong when weak, near when far. Make the enemy respond to illusions, not facts."},
        {"q": "What is the water doctrine?", "a": "As water shapes its course to the ground, strategy adapts to enemy and conditions — permanent principles, perpetually fresh application."},
    ],
    "chapters": [
        {
            "number": 1, "title": "Laying Plans — Calculate Before You Move",
            "page_start": 1, "page_end": 24, "duration_minutes": 22,
            "hook": "The general who calculates thoroughly before moving wins. The one who calculates little loses.",
            "chunks": [
                {"index": 1, "day": 1, "text": (
                    "Sun Tzu opens with a declaration that reframes everything: war is a matter of vital importance — "
                    "the road to survival or ruin. He identifies five fundamental factors that determine all strategic outcomes: "
                    "**Moral Law** (alignment between ruler and people — an army fighting for meaning is worth ten armies fighting for pay), "
                    "**Heaven** (timing and season — the general fighting against natural conditions fights on two fronts), "
                    "**Earth** (terrain — the soldier who knows the ground fights with confidence), "
                    "**The Commander** (wisdom, sincerity, benevolence, courage, strictness — remove any one and the commander becomes dangerous to his own forces), "
                    "and **Method and Discipline** (organisational structure and control — without method, courage collapses into chaos).\n\n"
                    "Before a campaign is launched, seven diagnostic questions must be answered: Which ruler has greater Moral Law? "
                    "Which commander has greater ability? Who has the advantages of Heaven and Earth? "
                    "On which side is discipline more rigorous? Which army is stronger? Who is better trained? "
                    "Where are reward and punishment more consistent?\n\n"
                    "The answers determine the outcome before a soldier moves. Victory and defeat are decided in the planning room, not the battlefield."
                )},
                {"index": 2, "day": 2, "text": (
                    "Sun Tzu closes the opening chapter with the paradox central to the entire text: plan everything, reveal nothing.\n\n"
                    "*'All warfare is based on deception. When able to attack, appear unable. When active, appear inactive. "
                    "When near, make the enemy believe you are far. When far, make them believe you are near.'*\n\n"
                    "A plan known to the enemy is a plan destroyed. Concealment gives the force of surprise — "
                    "consistently identified as the most powerful force multiplier in warfare.\n\n"
                    "The modern application is direct. In business, a strategy known to competitors is neutralised. "
                    "In negotiation, revealed intentions are exploited. In personal goals, loudly announced plans "
                    "invite interference and create the false sense of progress that kills motivation.\n\n"
                    "Calculate publicly with yourself. Move quietly. Strike decisively. "
                    "Let your results speak where your plans were silent."
                )},
            ],
            "summary": {
                "title": "Laying Plans: Victory Is Decided Before the Battle",
                "content": "Thorough calculation across five factors and seven diagnostic questions determines outcomes before action begins. Deception — appearing unlike reality — is the first weapon of the prepared strategist. Plan everything; reveal nothing.",
                "key_takeaways": ["Victory is won in the planning room, not the battlefield.", "Five factors and seven questions determine outcomes before a move is made.", "Deception controls what the enemy responds to — illusions, not facts.", "Conceal your dispositions; let results speak where plans were silent."],
            },
            "intelligence": {
                "skim": {"one_liner": "Calculate across five factors and seven questions before moving; all warfare is based on deception — plan everything, reveal nothing."},
                "concept": {"concepts": [
                    {"name": "Five Strategic Factors", "description": "Moral Law, Heaven, Earth, Commander, Method — the complete pre-battle assessment framework."},
                    {"name": "Seven Diagnostic Questions", "description": "Pre-battle checklist covering ruler alignment, commander ability, environmental advantage, discipline, strength, training, and reward consistency."},
                    {"name": "Strategic Deception", "description": "Appear unlike reality — weak when strong, near when far — to make the enemy respond to illusions rather than facts."},
                ]},
                "deep": {
                    "breakdown": "Sun Tzu's planning chapter is a decision-making framework for high-stakes environments. The five factors map to SWOT + environmental analysis. The seven questions are a pre-mortem checklist. The deception doctrine is what modern competitive intelligence calls 'information asymmetry management.'",
                    "examples": ["A smaller army knowing terrain and with strong Moral Law defeats a larger army in unfamiliar ground fighting for pay.", "A negotiator revealing nothing of their position while extracting the counterpart's constraints wins before the first offer."],
                    "analogy": "Planning without deception is a sword without a sheath — powerful but dangerously exposed.",
                },
                "exam": {"qa_pairs": [
                    {"question": "List Sun Tzu's five fundamental strategic factors.", "answer": "Moral Law, Heaven, Earth, the Commander, and Method (discipline/organisation)."},
                    {"question": "Why is all warfare based on deception?", "answer": "Appearing unlike reality forces the enemy to respond to illusions rather than facts — surrendering initiative to the deceiving party."},
                ]},
            },
        },
        {
            "number": 2, "title": "Attack by Stratagem — Win Without Fighting",
            "page_start": 25, "page_end": 52, "duration_minutes": 20,
            "hook": "Supreme excellence consists in breaking the enemy's resistance without fighting.",
            "chunks": [
                {"index": 3, "day": 3, "text": (
                    "Chapter 3 contains Sun Tzu's most quoted insight: *'Supreme excellence consists in breaking the enemy's resistance without fighting.'*\n\n"
                    "This is efficiency, not pacifism. Every battle consumes resources, time, and morale. "
                    "He ranks four levels of military excellence from highest to lowest: "
                    "**Attack the enemy's plans** (defeat strategy before execution), "
                    "**Disrupt their alliances** (isolate from support — a force cut off is already half-defeated), "
                    "**Attack their army in the field** (only when the first two fail — expensive in blood and treasure), "
                    "**Besiege their cities** (worst strategy — months of preparation for uncertain outcome; "
                    "*'a besieging force loses one-third of its men and the city may still not fall'*).\n\n"
                    "Intelligence and positioning come first. Force is the absolute last resort.\n\n"
                    "He follows with the most important strategic principle in the text: "
                    "*'Know your enemy and know yourself — in a hundred battles you will never be in peril. "
                    "Know yourself but not your enemy — for every victory, a defeat. Know neither — you will succumb in every battle.'*"
                )},
                {"index": 4, "day": 4, "text": (
                    "Sun Tzu closes with doctrine on force ratios — most applicable when facing a resource disadvantage:\n\n"
                    "*'If ten times the enemy's strength, surround him. Five times, attack. Twice, divide your forces. "
                    "Equal — offer battle. Fewer — be capable of retiring. In all respects unequal — avoid him.'*\n\n"
                    "This is strategic patience, not surrender. The smaller force that avoids decisive engagement "
                    "until achieving positional advantage eventually defeats the larger force that exhausts itself in pursuit. "
                    "History confirms this repeatedly: from guerrilla campaigns to startup disruptions of entrenched industries.\n\n"
                    "Sun Tzu's closing warning on leadership: "
                    "*'There are three ways a ruler brings misfortune upon his army: commanding advance when retreat is needed, "
                    "commanding retreat when advance is needed, and employing officers without knowledge of military affairs.'*\n\n"
                    "Civilian interference in expert execution, in any domain, is a force multiplier for the enemy."
                )},
            ],
            "summary": {
                "title": "Attack by Stratagem: Highest Victory Requires No Battle",
                "content": "The highest strategy makes battle unnecessary — attack plans first, alliances second, armies third, cities never. Combined self-knowledge and enemy intelligence eliminates peril. Smaller forces win through positioning and patience. Uninformed interference from leadership destroys expert execution.",
                "key_takeaways": ["Attack plans first, alliances second, armies third, cities never.", "Know yourself AND your enemy — self-knowledge alone is insufficient.", "Smaller forces win through positioning and patience, not raw strength.", "Uninformed leadership is a force multiplier for the enemy."],
            },
            "intelligence": {
                "skim": {"one_liner": "Win without fighting by attacking enemy plans first; complete intelligence (self + enemy) eliminates strategic peril; match force application to force ratio."},
                "concept": {"concepts": [
                    {"name": "Four Levels of Excellence", "description": "Attack plans → disrupt alliances → attack the army → besiege cities. Force is always the last resort."},
                    {"name": "Dual Intelligence Principle", "description": "Know yourself AND your enemy. Self-knowledge alone or enemy knowledge alone is insufficient for consistent victory."},
                    {"name": "Proportional Response", "description": "10:1 surround; 5:1 attack; 2:1 divide; equal engage; inferior avoid. Each force ratio demands a different strategic response."},
                ]},
                "deep": {
                    "breakdown": "The four levels of excellence map to modern competitive strategy: disrupting plans = product roadmap intelligence; disrupting alliances = cutting distribution; attacking the army = direct competition; sieging cities = market-share wars that drain both sides equally.",
                    "examples": ["A startup disrupts an incumbent by attacking its business model before the incumbent can adapt.", "A negotiator knowing their BATNA and the counterpart's constraints enters every negotiation without peril."],
                    "analogy": "Strategy without self-knowledge is navigating with a perfect map but no GPS — you know the territory but not where you stand in it.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What are Sun Tzu's four levels of military excellence?", "answer": "1) Attack enemy plans; 2) disrupt enemy alliances; 3) attack the army; 4) besiege cities. Force is always the last resort."},
                    {"question": "What does 'know yourself and your enemy' require in practice?", "answer": "Honest assessment of both your own capabilities/limitations AND the enemy's — self-knowledge alone or enemy knowledge alone is insufficient for consistent victory."},
                ]},
            },
        },
        {
            "number": 3, "title": "Positioning, Energy, and the Water Doctrine",
            "page_start": 53, "page_end": 96, "duration_minutes": 22,
            "hook": "Water shapes its course according to the ground — the soldier works out his victory in relation to the foe he faces.",
            "chunks": [
                {"index": 5, "day": 5, "text": (
                    "Sun Tzu introduces *shih* — strategic energy — and invincibility through defence:\n\n"
                    "*'The good fighters of old first put themselves beyond the possibility of defeat, "
                    "then waited for an opportunity to defeat the enemy.'* Security first. Opportunity second. "
                    "The general who attacks seeking victory without first ensuring invincibility is gambling — "
                    "and gamblers eventually lose everything.\n\n"
                    "Shih is accumulated force — stored through patient defensive positioning, "
                    "like a drawn crossbow, and released in one decisive strike at the exact moment of maximum enemy vulnerability. "
                    "Premature action dissipates shih. Patient positioning builds it until the moment of release makes the outcome inevitable.\n\n"
                    "He closes with strategic measurement: *'The victorious army is like a pound weighed against a grain; "
                    "the defeated army like a grain against a pound.'* Victory is not improvisation — "
                    "it is the result of deliberately constructed asymmetry deployed against a precisely chosen weak point."
                )},
                {"index": 6, "day": 6, "text": (
                    "Sun Tzu closes the entire text with the most important teaching of all:\n\n"
                    "*'Water shapes its course according to the nature of the ground over which it flows; "
                    "the soldier works out his victory in relation to the foe he is facing.'*\n\n"
                    "The strategist has no fixed method, no universal tactic. The method emerges from terrain, enemy, moment, "
                    "and the commander's own strengths. To mechanically apply strategy is to lose it.\n\n"
                    "*'Just as water retains no constant shape, so in warfare there are no constant conditions.'*\n\n"
                    "The principles in this text are permanent. Their application is perpetually fresh. "
                    "The student who memorises these principles and applies them rigidly has understood nothing. "
                    "The student who internalises them and applies them fluidly to every novel situation has understood everything.\n\n"
                    "Two and a half thousand years later, this remains the most important lesson in The Art of War: "
                    "not the tactics — the thinking."
                )},
            ],
            "summary": {
                "title": "Positioning, Shih, and Adaptation",
                "content": "Invincibility through patient defence precedes any offensive action. Strategic energy (shih) is accumulated through positioning and released in one decisive stroke. The final, supreme principle: adapt like water — permanent principles, perpetually fresh application. Mechanical strategy is guaranteed failure.",
                "key_takeaways": ["Secure against defeat first; seek victory second.", "Shih accumulates through patient positioning and releases in one decisive, inevitable strike.", "Mechanical application of strategy is guaranteed failure.", "Water doctrine: permanent principles, perpetually novel application."],
            },
            "intelligence": {
                "skim": {"one_liner": "Secure invincibility first; release accumulated shih in one decisive strike; adapt like water — permanent principles, perpetually fresh application."},
                "concept": {"concepts": [
                    {"name": "Defence-First Doctrine", "description": "Invincibility lies in defence. The enemy creates the opportunity for attack — it is not seized by will alone."},
                    {"name": "Shih", "description": "Strategic energy accumulated through patient positioning, released in one decisive stroke at the enemy's moment of maximum vulnerability."},
                    {"name": "Water Doctrine", "description": "No fixed form, no fixed method — permanent principles applied fluidly to perpetually novel conditions."},
                ]},
                "deep": {
                    "breakdown": "The water doctrine immunises the reader against the biggest failure mode in strategy: confusing the map for the territory. Shih maps to competitive moat theory — sustainable advantage built slowly, released decisively.",
                    "examples": ["A company building product, distribution, and brand before entering a market wins the measurement war before the first sale.", "A startup that avoids direct confrontation with the incumbent — attacking the flank instead of the fortress — wins what a frontal assault would have lost."],
                    "analogy": "Shih is compound interest for strategy — built slowly and almost invisibly through patient positioning, then released in a moment that looks to observers like effortless brilliance.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is shih and how is it built?", "answer": "Strategic energy accumulated through patient positioning and discipline. Built slowly through defensive manoeuvre; released in one decisive offensive strike at the precisely right moment."},
                    {"question": "What does the water doctrine mean as Sun Tzu's closing principle?", "answer": "As water shapes itself to the ground, strategy must adapt to enemy and conditions. The principles are permanent; their application must be perpetually fresh. Mechanical application guarantees failure."},
                ]},
            },
        },
    ],
})

# ─── MAN'S SEARCH FOR MEANING ─────────────────────────────────────────────────
MANS_SEARCH.update({
    "title": "Man's Search for Meaning",
    "author": "Viktor E. Frankl",
    "category": "Psychology & Philosophy",
    "total_pages": 165,
    "readers_count": 12_000_000,
    "rating": 4.8,
    "cover_image_url": "https://m.media-amazon.com/images/I/71yRt2WPBSL._AC_UY218_.jpg",
    "is_recommended": True, "is_trending": False,
    "reading_mode": "deep", "daily_minutes": 25,
    "book_type": "psychology", "complexity_level": "intermediate", "badge": "PROFOUND",
    "description": "Viktor Frankl, a psychiatrist who survived Auschwitz, wrote this account of how meaning — not pleasure, not power — is the primary human motivator. Part memoir, part psychological treatise, it is one of the most influential books of the 20th century.",
    "book_brief": {
        "what": "A psychiatrist's memoir of surviving Auschwitz combined with a complete theory of meaning as the primary human motivator.",
        "who": "Anyone grappling with suffering, purpose, or the question of what makes life worth living.",
        "core_argument": "Everything can be taken from a person except the last human freedom — the freedom to choose one's attitude toward any given set of circumstances.",
        "top_5_ideas": [
            "Meaning, not pleasure or power, is the primary human motivator (the will to meaning).",
            "The last human freedom is the choice of attitude toward unavoidable suffering.",
            "Suffering ceases to be suffering when it finds meaning.",
            "Logotherapy: meaning is found through work, love, or chosen attitude toward suffering.",
            "Those with a 'why' can bear almost any 'how'.",
        ],
        "verdict": "One of the most important books ever written. Read it when life is good so it's already inside you when it isn't.",
    },
    "flashcards": [
        {"q": "What is logotherapy?", "a": "Frankl's therapeutic approach centred on the idea that the primary human drive is the search for meaning — not pleasure (Freud) or power (Adler). The therapist helps patients find meaning in their lives."},
        {"q": "What is the 'last human freedom' according to Frankl?", "a": "The freedom to choose one's attitude toward any set of circumstances — the space between stimulus and response that cannot be taken away even by the worst suffering."},
        {"q": "What are the three pathways to meaning?", "a": "Through work (creating or accomplishing), through love (deep connection with another), or through chosen attitude toward unavoidable suffering."},
        {"q": "What is the existential vacuum?", "a": "The widespread emptiness and purposelessness in modern life caused by frustrated will to meaning — not material deprivation."},
        {"q": "What distinguished survivors in the camps?", "a": "Not physical strength but the presence of meaning — a person to return to, a task to complete, a purpose that gave their suffering a reason."},
    ],
    "chapters": [
        {
            "number": 1, "title": "Experiences in a Concentration Camp",
            "page_start": 1, "page_end": 88, "duration_minutes": 40,
            "hook": "Everything can be taken from a person but one thing: the freedom to choose one's attitude toward any given set of circumstances.",
            "chunks": [
                {"index": 1, "day": 1, "text": (
                    "Frankl begins not with theory but with experience — the account of arrival at Auschwitz. "
                    "The stripping of identity is systematic: name replaced by number, possessions confiscated, hair shaved. "
                    "The SS officers process new arrivals with casual brutality that communicates, without words, "
                    "that these people have ceased to be persons.\n\n"
                    "Frankl observes — with the detached precision of a trained psychiatrist — the psychological phases prisoners move through. "
                    "First, shock, which carries a certain mercy: the mind cannot yet fully process what is happening. "
                    "Second, apathy — a protective emotional blunting that allows witnessing horrors that would otherwise produce madness.\n\n"
                    "But within this systematic dehumanisation, Frankl makes the discovery that becomes the foundation of everything that follows: "
                    "*even in these conditions, some people maintained their inner freedom.* "
                    "Not freedom of movement or from hunger — but the freedom of how to respond. "
                    "He watches prisoners share their last piece of bread. He sees men comfort others while suffering equally. "
                    "These were not saints. They had simply discovered that the last human freedom cannot be confiscated."
                )},
                {"index": 2, "day": 2, "text": (
                    "Frankl recounts the moment he identifies the principle that would become logotherapy.\n\n"
                    "A fellow prisoner has lost all hope — wife dead, children gone, life's work destroyed. "
                    "Frankl does not offer comfort or philosophical argument. He asks a single question: "
                    "*'Is there still something — anything — that is waiting for you to do it? Someone who needs you?'*\n\n"
                    "The man pauses. Then answers: a book. Half-written. Waiting.\n\n"
                    "That conversation does not resolve his grief or make suffering less. "
                    "But it reconnects him to a future that requires his existence — and that is enough to carry him through the next day.\n\n"
                    "Frankl writes: *'It did not really matter what we expected from life, but what life expected from us. "
                    "We needed to stop asking about the meaning of life and instead think of ourselves as those "
                    "who were being questioned by life — daily and hourly.'*\n\n"
                    "The reframe is complete: not 'what do I get from life' but 'what does life require of me'."
                )},
            ],
            "summary": {
                "title": "Experiences in a Concentration Camp: The Last Human Freedom",
                "content": "Frankl's account of Auschwitz is simultaneously a memoir and a psychological observation study. His central discovery: even under total oppression, some maintained inner freedom — the freedom to choose their attitude. Those with a reason to live endured what those without purpose could not.",
                "key_takeaways": ["The last human freedom — choosing one's attitude — cannot be confiscated.", "Those with a 'why' can bear almost any 'how'.", "Love and connection to meaning are survival mechanisms, not luxuries.", "Reframe: not 'what do I expect from life' but 'what does life expect from me'."],
            },
            "intelligence": {
                "skim": {"one_liner": "Even in Auschwitz, those who retained meaning — a person, a task, a purpose — endured what those without it could not; the last human freedom is the choice of attitude toward any circumstance."},
                "concept": {"concepts": [
                    {"name": "Last Human Freedom", "description": "The freedom to choose one's attitude toward any circumstances — the space between stimulus and response that no external force can remove."},
                    {"name": "Will to Meaning", "description": "Meaning — not pleasure (Freud) or power (Adler) — is the primary human motivator. Those with purpose endure what those without it cannot."},
                    {"name": "Life's Question", "description": "Reframe: not 'what do I expect from life' but 'what does life expect from me' — transforming from passive recipient to active respondent."},
                ]},
                "deep": {
                    "breakdown": "Frankl's concentration camp observations form the most extreme natural experiment in human psychology ever documented. His finding — that inner freedom persists under total external oppression — challenges every purely materialist theory of motivation.",
                    "examples": ["Frankl thinking of his wife during the death march — love as survival mechanism.", "The prisoner with the half-written book — an unfinished task as reason to continue."],
                    "analogy": "Meaning is the keel of a ship in a storm. It doesn't stop the waves. But it keeps the vessel upright — and points it in a direction that makes survival purposeful.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is Frankl's 'last human freedom'?", "answer": "The freedom to choose one's attitude toward any given set of circumstances — the irreducible space between stimulus and response that no external force can take away."},
                    {"question": "What distinguished those who survived the camps longest?", "answer": "Not physical strength but the presence of meaning — a person to return to, a task to complete, a purpose that gave their suffering a reason."},
                ]},
            },
        },
        {
            "number": 2, "title": "Logotherapy in a Nutshell",
            "page_start": 89, "page_end": 138, "duration_minutes": 35,
            "hook": "Logotherapy focuses on the future — on the meanings to be fulfilled. It is therapy through meaning, not symptom relief.",
            "chunks": [
                {"index": 3, "day": 3, "text": (
                    "Logotherapy — from the Greek *logos* (meaning) — rests on three pillars:\n\n"
                    "**Freedom of Will.** Human beings have genuine freedom to choose their attitude toward any set of conditions. "
                    "Frankl watched prisoners in identical conditions make radically different choices about who they would be in those conditions.\n\n"
                    "**Will to Meaning.** The primary human motivator is not pleasure (Freud) or power (Adler) but the will to find meaning. "
                    "When frustrated, the result is the *existential vacuum*: a pervasive emptiness and purposelessness "
                    "that afflicts people whose material needs are fully met.\n\n"
                    "**Meaning of Life.** Life has meaning under all circumstances — even in suffering. "
                    "The task is not to create meaning arbitrarily but to *discover* it: meaning already present in the specific situation, "
                    "waiting for the person who asks the right question.\n\n"
                    "Three pathways always lead to meaning: through work (creating or accomplishing something), "
                    "through love (deeply connecting with another person and seeing their unique potential), "
                    "and through suffering — choosing one's attitude toward unavoidable pain, transforming endurance into testimony of human dignity."
                )},
                {"index": 4, "day": 4, "text": (
                    "Frankl addresses the existential vacuum — the dominant psychological condition of modern life.\n\n"
                    "Unlike the neurosis of Freud's era (repressed instinct finding indirect expression), "
                    "the mass condition of the 20th century onward is boredom, emptiness, and purposelessness "
                    "in people whose material needs are fully met. He observes the *Sunday depression*: "
                    "on weekdays, people are distracted by work. On Sunday afternoons — with leisure and no obligations — "
                    "the emptiness becomes undeniable.\n\n"
                    "The cure is not more entertainment or stimulation — both of which feed the problem. "
                    "The cure is the *will to meaning*: the deliberate pursuit of something larger than the self — "
                    "a cause, a person, a creative project — that makes demands upon you and therefore gives you a reason "
                    "to rise to the level it requires.\n\n"
                    "Frankl's most counterintuitive insight: happiness cannot be pursued directly. "
                    "It ensues as the *by-product* of a life lived in service of meaning. "
                    "The more directly you pursue it, the more it recedes."
                )},
            ],
            "summary": {
                "title": "Logotherapy: Therapy Through Meaning",
                "content": "Logotherapy rests on three pillars: freedom of will, will to meaning, and universal availability of meaning. Three pathways lead to meaning: work, love, and chosen attitude toward unavoidable suffering. The existential vacuum is the dominant modern condition — more pleasure makes it worse. Happiness is a by-product of meaningful life, never a direct goal.",
                "key_takeaways": ["Primary human motivator is meaning — not pleasure or power.", "Meaning found through work, love, or chosen attitude toward suffering.", "The existential vacuum (Sunday depression) is cured by pursuing meaning, not pleasure.", "Happiness cannot be pursued directly — it ensues as the by-product of a meaningful life."],
            },
            "intelligence": {
                "skim": {"one_liner": "Meaning — through work, love, or chosen attitude toward suffering — is the primary human motivator; happiness is a by-product, never a direct goal."},
                "concept": {"concepts": [
                    {"name": "Three Pillars of Logotherapy", "description": "Freedom of will; will to meaning (primary motivator); meaning available under all circumstances including suffering."},
                    {"name": "Three Pathways to Meaning", "description": "Through work (creating/accomplishing), through love (deep connection), through suffering (choosing attitude toward unavoidable pain)."},
                    {"name": "Existential Vacuum", "description": "Pervasive emptiness when the will to meaning is frustrated — the dominant psychological condition of modern comfortable life."},
                ]},
                "deep": {
                    "breakdown": "Frankl's logotherapy is a direct challenge to Freudian and Adlerian psychology. His therapeutic method (dereflection, paradoxical intention) redirects attention from symptom to meaning — the opposite of symptom-focused therapy. Maps to modern positive psychology's distinction between hedonic (pleasure) and eudaimonic (meaning/flourishing) well-being.",
                    "examples": ["A successful executive with depression not from failure but from achieved success — all goals reached, nothing left to pursue (existential vacuum).", "A prisoner with an unfinished book — meaning through work even in extremity."],
                    "analogy": "Meaning is the north star of human life. It doesn't make the journey easier. But it tells you which direction to walk — and that is enough.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What are the three pillars of logotherapy?", "answer": "Freedom of will (to choose attitude), will to meaning (primary motivator), and meaning of life (available under all circumstances including suffering)."},
                    {"question": "What is the existential vacuum and what causes it?", "answer": "Pervasive emptiness and purposelessness caused when the will to meaning is frustrated. Common despite material comfort — more pleasure makes it worse, not better."},
                ]},
            },
        },
        {
            "number": 3, "title": "The Case for a Tragic Optimism",
            "page_start": 139, "page_end": 165, "duration_minutes": 25,
            "hook": "The optimism I am speaking of is not naive. It is the capacity to say Yes to life in spite of everything.",
            "chunks": [
                {"index": 5, "day": 5, "text": (
                    "Frankl's postscript introduces *tragic optimism*: the capacity to say yes to life in spite of its unavoidable suffering, guilt, and death. "
                    "Not naive optimism — the tested optimism of someone who has faced the worst and discovered that meaning remains possible.\n\n"
                    "He identifies the tragic triad every human life must confront:\n\n"
                    "**Suffering** — unavoidable pain. Tragic optimism transforms it into human achievement.\n\n"
                    "**Guilt** — the irreversible past. Tragic optimism transforms it into motivation to change.\n\n"
                    "**Death** — the transience of all experience. Tragic optimism transforms it into the incentive to act responsibly now.\n\n"
                    "The key word in all three is *despite* — not because of these challenges, but in spite of them.\n\n"
                    "His final image: the human being as a statue carved from marble. "
                    "Each blow of the chisel — each suffering, each guilt, each loss — removes what is unnecessary "
                    "and reveals what was always there. The finished form was present in the stone from the beginning. "
                    "The question is only whether the carving is done consciously — or left to chance."
                )},
                {"index": 6, "day": 6, "text": (
                    "Frankl closes with his most demanding message:\n\n"
                    "*'Live as if you were living already for the second time and as if you had acted the first time "
                    "as wrongly as you are about to act now.'*\n\n"
                    "This thought experiment — imagining you are already living life for the second time with the chance "
                    "to correct a wrong decision — activates the full weight of responsibility in every present moment. "
                    "It is not self-punishment. It is the sharpest possible focus on now.\n\n"
                    "He notes that freedom without responsibility becomes nihilism. "
                    "The person who accepts responsibility — to a person, to a cause, to the quality of their own character — "
                    "has, paradoxically, more inner freedom than the person who accepts none.\n\n"
                    "The book ends where it began: between stimulus and response, there is a space. "
                    "However small, however compressed by circumstance. In that space lies human freedom. "
                    "In freedom lies the possibility of meaning. And in meaning — everything."
                )},
            ],
            "summary": {
                "title": "Tragic Optimism: Yes to Life in Spite of Everything",
                "content": "Tragic optimism — tested, not naive — is the capacity to affirm life despite suffering, guilt, and death. Each challenge is transformable into a source of meaning. Happiness arrives only as a by-product of responsibility and service. The second-time thought experiment activates full present-moment responsibility. Between stimulus and response lies a space — and in that space lies everything.",
                "key_takeaways": ["Tragic optimism: say Yes to life through and in spite of its suffering.", "The tragic triad (suffering, guilt, death) can each be transformed into a source of meaning.", "Responsibility gives freedom its shape — the voluntary acceptance of obligation is liberation.", "Between stimulus and response lies a space — and in that space lies everything."],
            },
            "intelligence": {
                "skim": {"one_liner": "Tragic optimism is the capacity to say yes to life in spite of suffering, guilt, and death — transforming each into meaning; responsibility is the practical form of freedom."},
                "concept": {"concepts": [
                    {"name": "Tragic Triad", "description": "Suffering, guilt, and death — unavoidable challenges, each transformable into meaning through chosen attitude."},
                    {"name": "Tragic Optimism", "description": "Tested optimism — the capacity to affirm life despite its worst circumstances because meaning remains available even in tragedy."},
                    {"name": "Second-Time Thought Experiment", "description": "Imagine living life for the second time, correcting a wrong decision you are about to make. Activates full present-moment responsibility."},
                ]},
                "deep": {
                    "breakdown": "Frankl's tragic optimism maps to modern positive psychology's eudaimonic well-being. It is optimism not of circumstances ('things will get better') but of will ('I can find meaning regardless of whether they do').",
                    "examples": ["A person who loses everything but responds with grace and purpose — the tragic optimist in action.", "Viktor Frankl himself: lost wife, family, manuscripts — but wrote the book that has given meaning to millions."],
                    "analogy": "Tragic optimism is a tree with deep roots — it bends in the storm of suffering, guilt, and death, but its roots hold. The tree without roots blows away; the one that cannot bend breaks.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is the tragic triad and how does logotherapy address each element?", "answer": "Suffering (transformed into achievement), guilt (transformed into motivation to change), death (transformed into incentive for responsible action). Each becomes a source of meaning through chosen attitude."},
                    {"question": "What is the second-time thought experiment?", "answer": "Imagine living life for the second time with the chance to correct a wrong decision you are about to make. Activates the full weight of present-moment responsibility."},
                ]},
            },
        },
    ],
})

# ─── THE ART OF HAPPINESS ─────────────────────────────────────────────────────
ART_OF_HAPPINESS.update({
    "title": "The Art of Happiness",
    "author": "Dalai Lama & Howard C. Cutler",
    "category": "Philosophy & Well-being",
    "total_pages": 322,
    "readers_count": 5_000_000,
    "rating": 4.5,
    "cover_image_url": "https://m.media-amazon.com/images/I/71HqSp9AJFL._AC_UY218_.jpg",
    "is_recommended": True, "is_trending": False,
    "reading_mode": "deep", "daily_minutes": 25,
    "book_type": "philosophy", "complexity_level": "beginner", "badge": "BESTSELLER",
    "description": "Based on a series of conversations between the Dalai Lama and psychiatrist Howard Cutler, this book explores the nature of happiness from both Buddhist and Western perspectives. Practical, warm, and deeply researched.",
    "book_brief": {
        "what": "A conversation between the Dalai Lama and a Western psychiatrist exploring the nature of happiness, compassion, and suffering.",
        "who": "Anyone seeking a practical, cross-cultural framework for well-being that goes beyond positive thinking.",
        "core_argument": "The purpose of life is happiness. Compassion — not pleasure-seeking — is its most reliable path.",
        "top_5_ideas": [
            "The purpose of existence is to seek happiness — this is the Dalai Lama's starting premise.",
            "Happiness is determined more by state of mind than by external conditions.",
            "Compassion for others is simultaneously the path to one's own happiness.",
            "Suffering is transformed by changing perspective, not by eliminating difficulty.",
            "Inner discipline — training the mind through practice — is the foundation of lasting well-being.",
        ],
        "verdict": "Deceptively profound. The Dalai Lama's directness and warmth make Buddhist wisdom immediately applicable.",
    },
    "flashcards": [
        {"q": "What is the Dalai Lama's starting premise?", "a": "The very purpose of our existence is to seek happiness — not pleasure alone, but genuine, lasting well-being that includes mental peace and compassion."},
        {"q": "What does the Dalai Lama say about happiness and external conditions?", "a": "Happiness is determined more by one's state of mind than by external conditions. Two people in identical circumstances can experience completely different levels of well-being."},
        {"q": "How does compassion lead to one's own happiness?", "a": "Compassion for others eliminates the self-preoccupation that generates most human suffering. When we genuinely care about others' well-being, our own anxiety and fear diminish naturally."},
        {"q": "What is the role of suffering in the Art of Happiness?", "a": "Suffering is an inevitable part of life. The question is not how to eliminate it but how to respond to it — changing perspective and finding meaning in difficulty rather than resisting it."},
        {"q": "What does 'inner discipline' mean in this framework?", "a": "The systematic training of the mind through practices like meditation, reflection, and the deliberate cultivation of compassion, patience, and equanimity."},
    ],
    "chapters": [
        {
            "number": 1, "title": "The Right to Happiness",
            "page_start": 1, "page_end": 42, "duration_minutes": 30,
            "hook": "I believe that the very purpose of our existence is to seek happiness.",
            "chunks": [
                {"index": 1, "day": 1, "text": (
                    "The Dalai Lama opens every conversation the same way: with warmth, attention, and the statement that "
                    "every human being has the right to happiness and the desire to overcome suffering. "
                    "This is not a religious claim — it is an observation. Every action every person has ever taken "
                    "was motivated, at some level, by the desire to experience well-being and avoid pain.\n\n"
                    "What separates people is not whether they want happiness — everyone does — but whether they know "
                    "how to pursue it effectively. Most people, the Dalai Lama observes with gentle candour, "
                    "spend their lives pursuing happiness in ways guaranteed to produce its opposite: "
                    "accumulating possessions that require maintenance, building identities that require defence, "
                    "seeking approval from people whose own happiness is equally fragile.\n\n"
                    "His first practical distinction: happiness from external sources versus happiness from internal sources. "
                    "External happiness — pleasure, status, acquisition — is real but unreliable. "
                    "It depends on conditions outside your control and fades when those conditions change. "
                    "Internal happiness — equanimity, compassion, meaning — is built through practice and is "
                    "not vulnerable to the same fluctuations. This distinction becomes the spine of the entire book."
                )},
                {"index": 2, "day": 2, "text": (
                    "Howard Cutler, the Western psychiatrist co-authoring this book, presses the Dalai Lama "
                    "on a question that his Western training makes unavoidable: "
                    "isn't it unrealistic to suggest that happiness is achievable for everyone, "
                    "given that so many people suffer from clinical depression, trauma, or circumstances "
                    "of genuine deprivation?\n\n"
                    "The Dalai Lama's response is both compassionate and direct. He does not deny the reality of "
                    "mental illness or poverty. He acknowledges that some people face genuine chemical or "
                    "circumstantial obstacles that require professional help or material change.\n\n"
                    "But he makes a careful distinction between *suffering caused by external conditions* "
                    "and *suffering caused by mental states.* The first may require external solutions. "
                    "The second — which he argues constitutes the vast majority of human misery — "
                    "responds to inner work. Anxiety about the future, rumination about the past, "
                    "comparison with others, fear of loss — none of these require external conditions to change. "
                    "They require the mind that generates them to be trained differently."
                )},
            ],
            "summary": {
                "title": "The Right to Happiness",
                "content": "Every human being seeks happiness and wishes to avoid suffering. Most pursue happiness through external means that are inherently unreliable. The Dalai Lama's central teaching: happiness from internal sources — built through deliberate mental training — is more durable and controllable than happiness dependent on external conditions.",
                "key_takeaways": ["Every human being has the right to happiness and the desire to avoid suffering.", "Most pursue happiness through external means that are inherently unreliable.", "Internal happiness (equanimity, compassion) is more durable than external happiness (pleasure, status).", "Suffering from mental states — the majority of human misery — responds to inner work."],
            },
            "intelligence": {
                "skim": {"one_liner": "The purpose of existence is to seek happiness; internal happiness (built through mental training) is more durable and reliable than external happiness (pleasure, acquisition, status)."},
                "concept": {"concepts": [
                    {"name": "Two Sources of Happiness", "description": "External (pleasure, status, acquisition — real but unreliable, dependent on conditions) vs internal (equanimity, compassion — built through practice, not vulnerable to external fluctuation)."},
                    {"name": "Universal Desire", "description": "Every human action is ultimately motivated by the desire for well-being and the wish to avoid suffering — the common ground beneath all apparent differences."},
                    {"name": "Mental Training", "description": "The systematic cultivation of positive mental states (compassion, patience, equanimity) through deliberate practice — the Dalai Lama's prescription for lasting happiness."},
                ]},
                "deep": {
                    "breakdown": "The Dalai Lama's framework maps precisely onto what positive psychology calls 'hedonic adaptation' — the well-documented finding that external improvements (more money, better circumstances) produce only temporary happiness increases before the mind returns to its baseline. Internal training, by contrast, can raise the baseline itself.",
                    "examples": ["People who win the lottery report similar happiness levels to their pre-win state within two years.", "Meditation practitioners show measurable baseline increases in positive affect regardless of external circumstances."],
                    "analogy": "External happiness is like borrowed furniture — it fills the room but you can't keep it forever. Internal happiness is like building the room itself — it stays regardless of what furniture comes and goes.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is the Dalai Lama's distinction between external and internal happiness?", "answer": "External happiness (pleasure, status, acquisition) is real but unreliable — dependent on conditions outside your control. Internal happiness (equanimity, compassion) is built through deliberate mental practice and is not vulnerable to the same fluctuations."},
                    {"question": "What does the Dalai Lama say about suffering from mental states vs external conditions?", "answer": "Suffering from external conditions may require external solutions. But suffering from mental states — anxiety, rumination, comparison, fear — constitutes the vast majority of human misery and responds to inner work, not external change."},
                ]},
            },
        },
        {
            "number": 2, "title": "Compassion — The Foundation of Happiness",
            "page_start": 43, "page_end": 128, "duration_minutes": 40,
            "hook": "If you want others to be happy, practise compassion. If you want to be happy, practise compassion.",
            "chunks": [
                {"index": 3, "day": 3, "text": (
                    "The Dalai Lama makes a claim that surprises most Western readers: "
                    "**compassion for others is simultaneously the most reliable path to one's own happiness.**\n\n"
                    "This sounds paradoxical until he explains the mechanism. Most human suffering — anxiety, loneliness, "
                    "fear, resentment — is generated by excessive self-focus. When the mind is constantly oriented "
                    "toward 'what about me? what do I need? what do I fear losing?' it creates a contracted, "
                    "defensive, anxious state that is the opposite of happiness.\n\n"
                    "When genuine compassion for others arises — when the mind genuinely orients toward "
                    "'what does this person need? how can I help?' — the self-preoccupation that generates "
                    "most suffering naturally falls away. The mind becomes spacious, warm, and expansive. "
                    "The anxiety of self-protection gives way to the energy of care.\n\n"
                    "He is careful to distinguish compassion from pity. Pity looks down at suffering from a distance. "
                    "Compassion sits with suffering as an equal — feeling with, not feeling for. "
                    "It includes the recognition that the other person's suffering is as real and urgent as your own."
                )},
                {"index": 4, "day": 4, "text": (
                    "Cutler asks the question every Western reader is thinking: isn't it exhausting to feel everyone's suffering? "
                    "Isn't compassion on the Dalai Lama's scale a recipe for burnout?\n\n"
                    "The answer is the most important distinction in the chapter: "
                    "**empathic distress vs compassion.**\n\n"
                    "Empathic distress is the experience of absorbing another's suffering as if it were your own — "
                    "losing oneself in the pain of others, which does produce exhaustion and eventually withdrawal. "
                    "This is what many people mean when they say 'I'm too empathetic — I feel everything too much.'\n\n"
                    "Genuine compassion is fundamentally different. It maintains the equanimity of the observer "
                    "while genuinely caring about the other's well-being. It is stable, not destabilising. "
                    "The Dalai Lama uses the image of a surgeon: a good surgeon cares deeply about the patient "
                    "but must maintain steady hands. Care without equanimity produces neither good surgery nor good compassion.\n\n"
                    "The practical implication: compassion can be trained, and training it is protective of the self, "
                    "not destructive of it."
                )},
            ],
            "summary": {
                "title": "Compassion: The Most Reliable Path to Happiness",
                "content": "Compassion for others is simultaneously the most reliable path to one's own happiness — not despite self-interest but because of it. Self-preoccupation generates most human suffering; compassion naturally dissolves it. The distinction between empathic distress (absorbing others' pain) and genuine compassion (caring with equanimity) explains why the Dalai Lama's compassion is energising rather than exhausting.",
                "key_takeaways": ["Compassion for others is the most reliable path to your own happiness — dissolves self-preoccupation.", "Distinguish empathic distress (absorbing pain) from compassion (caring with equanimity).", "Compassion is a trainable skill — training it is protective, not draining.", "Self-focus generates suffering; other-focus generates spaciousness and warmth."],
            },
            "intelligence": {
                "skim": {"one_liner": "Compassion for others is the most reliable path to your own happiness — it dissolves the self-preoccupation that generates most suffering; distinguish empathic distress from compassion with equanimity."},
                "concept": {"concepts": [
                    {"name": "Compassion as Self-Interest", "description": "Genuine care for others naturally dissolves the self-preoccupation that generates most human suffering — making compassion one of the most effective tools for personal happiness."},
                    {"name": "Empathic Distress vs Compassion", "description": "Empathic distress = absorbing others' pain as your own (exhausting, leads to withdrawal). Compassion = caring deeply while maintaining equanimity (energising, sustainable)."},
                    {"name": "Compassion Training", "description": "Compassion is a skill developed through deliberate practice — meditation, reflection, and the conscious expansion of care beyond one's immediate circle."},
                ]},
                "deep": {
                    "breakdown": "The distinction between empathic distress and compassion maps directly onto neuroscience: fMRI studies show that empathic distress activates pain circuits in the brain, while compassion meditation activates reward circuits. The Dalai Lama's intuition is confirmed: compassion is neurologically distinct from and less costly than empathic distress.",
                    "examples": ["A doctor who maintains equanimity while genuinely caring for patients can sustain 30 years of practice; one who absorbs patients' suffering directly typically burns out within 5-7 years.", "The Dalai Lama himself: regularly exposed to reports of suffering on a massive scale but consistently warm and energetic rather than depleted."],
                    "analogy": "Compassion is like a warm fire — it radiates heat to everyone near it, including the person tending it. Empathic distress is like putting your hand in the fire — you can't sustain it.",
                },
                "exam": {"qa_pairs": [
                    {"question": "Why does the Dalai Lama say compassion for others leads to your own happiness?", "answer": "Self-preoccupation generates most human suffering. Genuine compassion naturally dissolves it — when the mind orients toward others' well-being, the contracted, anxious self-focus that causes suffering falls away, producing spaciousness and warmth."},
                    {"question": "What is the difference between empathic distress and compassion?", "answer": "Empathic distress = absorbing others' pain as your own, which is exhausting and leads to withdrawal. Compassion = caring deeply about others' well-being while maintaining the equanimity of an observer — energising and sustainable."},
                ]},
            },
        },
        {
            "number": 3, "title": "Transforming Suffering",
            "page_start": 129, "page_end": 322, "duration_minutes": 50,
            "hook": "Pain is inevitable. Suffering is optional. The distinction is in how the mind relates to what happens.",
            "chunks": [
                {"index": 5, "day": 5, "text": (
                    "The Dalai Lama addresses suffering with a directness that many Western self-help books avoid: "
                    "some suffering is unavoidable, and trying to eliminate all of it is itself a source of suffering.\n\n"
                    "He identifies two categories. The first — physical pain, loss, grief — is real and must be acknowledged. "
                    "Trying to suppress or deny it creates secondary suffering on top of the primary. "
                    "The correct response is acceptance: sitting with pain as a real experience without either "
                    "dramatising it or pretending it isn't there.\n\n"
                    "The second category — the suffering added by the mind — is where genuine transformation is possible. "
                    "The anxiety that extends beyond actual threat. The resentment replayed long after the event. "
                    "The fear of loss that is more consuming than the actual loss would be. "
                    "These are mental productions, not objective realities — and they respond to inner work.\n\n"
                    "His key teaching on suffering: **perspective changes everything.** "
                    "The same event experienced by two people with different perspectives produces radically different suffering. "
                    "One person losing a job experiences it as catastrophe; another experiences it as liberation. "
                    "The event is identical. The suffering is not."
                )},
                {"index": 6, "day": 6, "text": (
                    "The Dalai Lama closes the book with a practical synthesis:\n\n"
                    "Happiness is not a destination. It is a practice — a daily orientation of the mind toward "
                    "compassion, gratitude, equanimity, and connection. It cannot be achieved once and maintained effortlessly. "
                    "Like physical fitness, it must be worked at continuously.\n\n"
                    "He offers a simple daily practice: begin each morning by setting an intention of compassion — "
                    "not as a vague feeling but as a specific commitment: *'Today, wherever possible, I will not harm others. "
                    "Where possible, I will help.'* This practice, repeated daily, gradually reshapes the default orientation "
                    "of the mind from self-protection to other-care — and in doing so, generates the internal happiness "
                    "that external circumstances can never reliably provide.\n\n"
                    "His final observation — delivered with the warmth and practicality that characterises the entire book — "
                    "is the simplest: *'If you want others to be happy, practise compassion. "
                    "If you want to be happy, practise compassion.'* "
                    "These two instructions, it turns out, are the same instruction."
                )},
            ],
            "summary": {
                "title": "Transforming Suffering Through Perspective and Practice",
                "content": "Some suffering is unavoidable; trying to eliminate all of it creates additional suffering. The distinction between primary pain (unavoidable) and secondary suffering (mental production) points to where transformation is possible: in the mind's relationship to events, not in the events themselves. Happiness is a daily practice, not a destination.",
                "key_takeaways": ["Some suffering is unavoidable — accept primary pain without dramatising or denying it.", "Secondary suffering (anxiety, resentment, fear) is a mental production that responds to inner work.", "Perspective changes everything — the same event produces radically different suffering depending on the mind's relationship to it.", "Happiness is a daily practice of compassion and equanimity, not a destination to be reached."],
            },
            "intelligence": {
                "skim": {"one_liner": "Primary pain is unavoidable — accept it; secondary suffering (anxiety, resentment) is a mental production that changes with perspective and practice; happiness is a daily orientation, not a destination."},
                "concept": {"concepts": [
                    {"name": "Primary Pain vs Secondary Suffering", "description": "Primary pain (loss, grief, physical injury) is unavoidable. Secondary suffering (anxiety, resentment, fear of loss) is added by the mind and responds to inner training."},
                    {"name": "Perspective as Transformation", "description": "The same event produces radically different suffering depending on the mind's relationship to it — perspective is not denial, it is reorientation."},
                    {"name": "Happiness as Daily Practice", "description": "Happiness is maintained through continuous daily orientation toward compassion, gratitude, and equanimity — like physical fitness, it requires ongoing work."},
                ]},
                "deep": {
                    "breakdown": "The Dalai Lama's distinction between primary pain and secondary suffering maps precisely onto ACT (Acceptance and Commitment Therapy) — the distinction between pain (inevitable) and suffering (the struggle against pain). Both frameworks prescribe acceptance of primary pain and defusion from the secondary mental productions.",
                    "examples": ["Viktor Frankl in the camps — same conditions, radically different responses based on inner orientation.", "Two people receiving the same critical feedback — one spirals, one improves. Same event; different relationship to it."],
                    "analogy": "Primary pain is the rain. Secondary suffering is running into the rain without clothes trying to fight it. Acceptance is standing in the rain with appropriate gear — present with it, not destroyed by it.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is the Dalai Lama's distinction between primary pain and secondary suffering?", "answer": "Primary pain (loss, grief, physical injury) is unavoidable and must be accepted. Secondary suffering (anxiety, resentment, fear) is added by the mind and responds to inner work — perspective, training, and practice."},
                    {"question": "What is the Dalai Lama's daily practice prescription?", "answer": "Begin each morning with an intention of compassion: 'Today, wherever possible, I will not harm others. Where possible, I will help.' This daily orientation gradually shifts the default state of the mind from self-protection to other-care."},
                ]},
            },
        },
    ],
})

# ─── THE RICHEST MAN IN BABYLON ───────────────────────────────────────────────
RICHEST_MAN.update({
    "title": "The Richest Man in Babylon",
    "author": "George S. Clason",
    "category": "Personal Finance",
    "total_pages": 144,
    "readers_count": 3_000_000,
    "rating": 4.6,
    "cover_image_url": "https://m.media-amazon.com/images/I/71MX5m0NYQL._AC_UY218_.jpg",
    "is_recommended": False, "is_trending": True,
    "reading_mode": "concept", "daily_minutes": 20,
    "book_type": "finance", "complexity_level": "beginner", "badge": "CLASSIC",
    "description": "Through engaging parables set in ancient Babylon, George Clason delivers timeless financial wisdom. The seven cures for a lean purse and the five laws of gold remain the clearest guide to building wealth ever written.",
    "book_brief": {
        "what": "Financial wisdom delivered through parables set in ancient Babylon — simple, timeless, actionable.",
        "who": "Anyone who wants to understand money management from first principles, regardless of current income.",
        "core_argument": "A part of all you earn is yours to keep. Start with 10%, invest it wisely, and let it grow.",
        "top_5_ideas": [
            "Pay yourself first: save at least 10% of all you earn before any other expense.",
            "Make your money work for you — let your savings generate income.",
            "Seek the counsel of those competent in money matters before investing.",
            "Protect your principal — guard against loss before seeking gain.",
            "The five laws of gold govern all wealth creation, in ancient Babylon and today.",
        ],
        "verdict": "Read in one sitting. The parables make timeless financial principles memorable and immediately applicable.",
    },
    "flashcards": [
        {"q": "What is the First Cure for a Lean Purse?", "a": "Start thy purse to fattening — save at least one-tenth of all you earn, every time, without exception. Pay yourself first."},
        {"q": "What is the Second Cure?", "a": "Control thy expenditures — live on the remaining nine-tenths. Budget to live within your means without feeling deprived."},
        {"q": "What is the Third Cure?", "a": "Make thy gold multiply — put savings to work through investments that generate reliable income."},
        {"q": "What does Arkad say about seeking counsel before investing?", "a": "Seek the advice of those experienced in profitable handling of gold. A bricklayer does not seek a jeweller's advice on bricklaying — nor should you take financial advice from someone inexperienced in finance."},
        {"q": "What are the Five Laws of Gold?", "a": "1) Gold comes to those who save a tenth; 2) gold multiplies for those who invest it; 3) gold clings to the cautious owner who takes counsel from experts; 4) gold escapes those who invest in businesses they don't understand; 5) gold flees those who force impossible returns or follow tricksters."},
    ],
    "chapters": [
        {
            "number": 1, "title": "The Man Who Desired Gold — Beginning of Wisdom",
            "page_start": 1, "page_end": 36, "duration_minutes": 22,
            "hook": "Arkad — the richest man in Babylon — was once as poor as any man. His secret was not talent. It was one decision.",
            "chunks": [
                {"index": 1, "day": 1, "text": (
                    "Arkad, the richest man in Babylon, is asked by his childhood friends how he came to possess such wealth "
                    "when they, who had equal intelligence and worked equally hard, remained poor.\n\n"
                    "His answer reframes everything: *'I found the road to wealth when I decided that a part of all I earn is mine to keep.'*\n\n"
                    "He discovered this principle from a money lender named Algamish, who asked him a question that changed his life: "
                    "*'A part of all you earn, is it yours to keep?'* Arkad answered that he kept what remained after expenses. "
                    "Algamish replied: *'That is why you have nothing. What you pay to others is not yours. "
                    "But what you keep — even one-tenth — that is yours.'*\n\n"
                    "The principle seems too simple to be life-changing. But Arkad observed that he had been spending "
                    "everything he earned, leaving nothing for himself. By keeping one-tenth before paying anyone else, "
                    "he began accumulating a growing store of gold that eventually found productive uses, "
                    "generating income that freed him from dependence on his labour alone."
                )},
                {"index": 2, "day": 2, "text": (
                    "Arkad teaches the Seven Cures for a Lean Purse to the citizens of Babylon, beginning with the most important:\n\n"
                    "**First Cure — Start thy purse to fattening.** For every ten coins you place in your purse, "
                    "spend but nine. Your purse will begin to fatten at once, and its weight will feel good in your hand.\n\n"
                    "**Second Cure — Control thy expenditures.** Budget the nine-tenths. Many things you desire are not necessary. "
                    "Confuse not necessary expenses with desires — study thy wants honestly.\n\n"
                    "**Third Cure — Make thy gold multiply.** Put savings to work at interest, so that it may breed more gold. "
                    "Gold resting in your purse earns nothing. Gold working for you earns while you sleep.\n\n"
                    "**Fourth Cure — Guard thy treasures from loss.** The first purpose of investing is the preservation of principal. "
                    "The penalty of risk is the loss of principal. Study your investments before committing — "
                    "and take counsel of those with experience in the profitable handling of gold."
                )},
            ],
            "summary": {
                "title": "The Man Who Desired Gold",
                "content": "Arkad reveals the simple principle behind his wealth: a part of all he earned was always his to keep. The first four cures — pay yourself first (10%), control expenditures, make gold multiply through investment, and guard against loss — form the complete foundation of personal wealth management.",
                "key_takeaways": ["A part of all you earn is yours to keep — save at least one-tenth, every time.", "Pay yourself first — before expenses, before desires, before anyone else.", "Make your gold multiply — savings sitting idle earn nothing; invested savings earn while you sleep.", "Guard against loss — preservation of principal is the first law of investment."],
            },
            "intelligence": {
                "skim": {"one_liner": "Save one-tenth of all you earn before any expense; make your savings work for you through investment; guard your principal before seeking gain — Babylon's timeless wealth formula."},
                "concept": {"concepts": [
                    {"name": "Pay Yourself First", "description": "Save 10% of every income before any other expense. This single habit is the foundation of all wealth building."},
                    {"name": "Seven Cures", "description": "Save 10%; control expenditures; invest savings; guard against loss; own your home; insure future income; increase your ability to earn."},
                    {"name": "Gold Multiplication", "description": "Savings must work — idle money earns nothing. Compounding investment income is the mechanism through which modest savings become significant wealth."},
                ]},
                "deep": {
                    "breakdown": "Clason's 'pay yourself first' principle predates Warren Buffett's teachings by 70 years and maps directly onto the modern concept of automatic savings — behavioural finance's finding that removing money from the decision-making process (automatically diverting it before spending) is more effective than relying on willpower.",
                    "examples": ["Arkad grew from scribe to richest man through one decision: keep one-tenth always.", "Modern equivalent: automatic transfer to savings/investment account on payday, before discretionary spending."],
                    "analogy": "Your income is a river. Most people let it run freely to the sea and wonder why the lake never fills. Arkad built a dam — one-tenth — and let the reservoir grow.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is Arkad's single most important financial principle?", "answer": "A part of all you earn is yours to keep — save at least one-tenth of every income, before any other expense, every time without exception."},
                    {"question": "What are the first four of the Seven Cures for a Lean Purse?", "answer": "1) Save one-tenth; 2) control expenditures (live on nine-tenths); 3) make savings multiply through investment; 4) guard principal against loss before seeking gain."},
                ]},
            },
        },
        {
            "number": 2, "title": "The Five Laws of Gold",
            "page_start": 37, "page_end": 96, "duration_minutes": 28,
            "hook": "Gold is governed by laws as certain as gravity. Obey them and gold will come. Ignore them and gold will flee.",
            "chunks": [
                {"index": 3, "day": 3, "text": (
                    "Kalabab, a wealthy merchant, tells his son the story of Nomasir — Arkad's son — "
                    "who was given a choice: take gold directly, or receive clay tablets engraved with the Five Laws of Gold.\n\n"
                    "Nomasir took both. He lost the gold quickly through inexperience. "
                    "The clay tablets saved him and eventually made him wealthier than he would have been "
                    "if he had kept the gold intact.\n\n"
                    "The Five Laws:\n\n"
                    "**First:** Gold comes gladly and in increasing quantity to any person who will save not less than "
                    "one-tenth of their earnings.\n\n"
                    "**Second:** Gold labours diligently and contentedly for the wise owner who finds for it profitable employment, "
                    "multiplying even as the flocks of the field.\n\n"
                    "**Third:** Gold clings to the protection of the cautious owner who invests it under the counsel of men "
                    "wise in its handling.\n\n"
                    "**Fourth:** Gold slips away from the man who invests it in businesses or purposes "
                    "with which he is not familiar or which are not approved by those skilled in its keep.\n\n"
                    "**Fifth:** Gold flees the man who would force it to impossible earnings or who follows "
                    "the alluring advice of tricksters and schemers."
                )},
                {"index": 4, "day": 4, "text": (
                    "Clason closes with the parable of the man who desired luck — and the profound teaching it contains.\n\n"
                    "Sharru Nada, the merchant prince of Babylon, teaches his grandson the truth behind apparent luck: "
                    "*'Luck is not chance. It is toil. The man who finds the purse of gold in the street "
                    "is not lucky — he is the man who placed himself where purses are dropped by being at work early "
                    "and home late.'*\n\n"
                    "He explains that what people call luck in wealth creation is almost always the intersection "
                    "of preparation and opportunity. The person who has saved consistently has capital available "
                    "when genuine opportunities arise. The person who has learned about investment recognises "
                    "those opportunities when others don't. The person who has built relationships with "
                    "experienced advisors has access to better counsel.\n\n"
                    "Luck, in Clason's framework, is not random. It is cultivated. "
                    "And the cultivation happens through precisely the Seven Cures and Five Laws: "
                    "consistent saving, wise investment, protection of principal, and the humility to seek "
                    "competent counsel."
                )},
            ],
            "summary": {
                "title": "The Five Laws of Gold",
                "content": "Gold obeys five laws: it comes to those who save, multiplies for those who invest it, clings to those who take wise counsel, slips from those who invest without knowledge, and flees from those chasing impossible returns or following tricksters. Luck is not chance — it is preparation meeting opportunity, cultivated through the consistent application of the laws.",
                "key_takeaways": ["Gold obeys laws — save consistently, invest wisely, seek competent counsel, guard principal.", "Fourth law: never invest in businesses or instruments you don't understand.", "Fifth law: gold flees those chasing impossible returns or following tricksters.", "Luck = preparation + opportunity; cultivated through consistent practice of the laws."],
            },
            "intelligence": {
                "skim": {"one_liner": "Gold obeys five laws: save to attract it, invest to multiply it, take wise counsel to keep it, never invest in what you don't understand, never chase impossible returns."},
                "concept": {"concepts": [
                    {"name": "Five Laws of Gold", "description": "Save (attracts gold) → invest (multiplies) → take counsel (protects) → avoid unfamiliar investments (fourth law) → avoid impossible returns/tricksters (fifth law)."},
                    {"name": "Counsel of the Wise", "description": "Seek advice only from those experienced in the profitable handling of gold — not friends, relatives, or enthusiastic promoters who lack that specific expertise."},
                    {"name": "Cultivated Luck", "description": "What appears as luck in wealth is preparation (savings, knowledge, relationships) meeting opportunity — consistently cultivated through the laws."},
                ]},
                "deep": {
                    "breakdown": "The fourth and fifth laws of gold map directly onto Warren Buffett's first two rules of investing: Rule 1 — never lose money; Rule 2 — never forget Rule 1. Both Clason and Buffett emphasise investing only within one's circle of competence and avoiding leverage and speculation.",
                    "examples": ["Nomasir lost his gold immediately through inexperience; the clay tablets (the laws) eventually made him wealthier.", "Modern equivalent: retail investors buying into assets they don't understand (crypto, options, meme stocks) and losing principal — violation of law four."],
                    "analogy": "The Five Laws of Gold are like the laws of navigation: ignore the stars and currents and you'll drift. Follow them with discipline and you'll reach any destination.",
                },
                "exam": {"qa_pairs": [
                    {"question": "State the Five Laws of Gold.", "answer": "1) Gold comes to those who save; 2) gold multiplies for those who invest; 3) gold clings to those who take wise counsel; 4) gold slips from those who invest in what they don't understand; 5) gold flees those who chase impossible returns or follow tricksters."},
                    {"question": "What does Clason mean by 'luck is not chance'?", "answer": "Luck in wealth is preparation (consistent saving, knowledge, wise counsel) meeting opportunity. It is cultivated through disciplined application of the laws, not randomly bestowed."},
                ]},
            },
        },
        {
            "number": 3, "title": "The Gold Lender of Babylon",
            "page_start": 97, "page_end": 144, "duration_minutes": 22,
            "hook": "Better a little caution than a great regret. The careful investor who loses nothing will eventually have more than the bold investor who loses often.",
            "chunks": [
                {"index": 5, "day": 5, "text": (
                    "Mathon the gold lender teaches his students the art of lending — and by extension, "
                    "the most practical guide to evaluating any investment:\n\n"
                    "Before lending, he evaluates three things:\n\n"
                    "**Purpose:** What does the borrower want the money for? A purpose that generates income "
                    "makes repayment likely. A purpose that consumes without producing makes default likely.\n\n"
                    "**Ability to repay:** Does the borrower have a reliable income or assets? "
                    "Good intentions are not collateral.\n\n"
                    "**Character:** Does the borrower have a history of fulfilling obligations? "
                    "A person who regularly pays their debts has demonstrated a character that "
                    "makes future repayment probable. A person who rationalises non-payment will continue to do so.\n\n"
                    "He notes that the wealthy merchants of Babylon do not take undue risks — "
                    "they invest where they can see the income stream clearly, not where they are promised spectacular returns "
                    "that strain credulity. *'Better a little caution than a great regret.'*"
                )},
                {"index": 6, "day": 6, "text": (
                    "Clason closes with the most overlooked financial principle in the book: "
                    "**the importance of investing in yourself before investing in anything else.**\n\n"
                    "The seventh cure — often skipped in summaries — is: *'Cultivate thy own powers, "
                    "to study and become wiser, to become more skilful, to so act as to respect thyself.'* "
                    "The greatest asset any person has is their ability to earn. "
                    "An increase in earning capacity produces more wealth over time than any investment.\n\n"
                    "The practical application: a tradesperson who masters their craft earns more than one who doesn't. "
                    "A salesperson who develops their skills outearns one of equal natural talent who doesn't. "
                    "A professional who continuously develops their knowledge makes themselves more valuable "
                    "to any organisation or client.\n\n"
                    "The compound returns on investing in your own skill and knowledge are, "
                    "over a working lifetime, greater than the returns on any financial asset — "
                    "because they raise the income that all other savings and investments depend upon."
                )},
            ],
            "summary": {
                "title": "The Gold Lender: Caution, Character, and the Seventh Cure",
                "content": "Sound investment requires evaluating purpose, ability to repay, and character before committing capital. The seventh and most overlooked cure: invest in yourself — cultivating skill, knowledge, and earning capacity. The compound returns on personal development exceed those of any financial asset over a working lifetime.",
                "key_takeaways": ["Evaluate purpose, ability to repay, and character before any investment.", "Better a little caution than a great regret — spectacular returns should strain credulity.", "The seventh cure: invest in yourself — increase earning capacity first.", "Compound returns on skill and knowledge exceed financial returns over a working lifetime."],
            },
            "intelligence": {
                "skim": {"one_liner": "Evaluate purpose, repayment ability, and character before any investment; invest in yourself first — the compound returns on skill exceed those of any financial asset."},
                "concept": {"concepts": [
                    {"name": "Three Investment Criteria", "description": "Purpose (income-producing vs consuming), ability to repay (reliable income or assets), character (history of fulfilling obligations) — Mathon's pre-lending framework."},
                    {"name": "Seventh Cure", "description": "Cultivate thy own powers — invest in skill, knowledge, and earning capacity before anything else. The greatest asset is the ability to earn."},
                    {"name": "Compounding Earning Capacity", "description": "Increasing your earning capacity through skill development raises the income that all savings and investments depend upon — the highest-return investment available."},
                ]},
                "deep": {
                    "breakdown": "Mathon's three criteria map precisely onto modern credit analysis: purpose (use of funds), capacity (debt service coverage), and character (credit history). Warren Buffett adds a fourth — competitive advantage — but the first three have been used in Babylon and Wall Street alike.",
                    "examples": ["Mathon: lends freely to the merchant with a track record and productive purpose; cautiously to the farmer with good character but uncertain harvest.", "Modern: a mortgage lender evaluating income, purpose of loan, and credit history is using Mathon's framework 2,500 years later."],
                    "analogy": "Lending without evaluating character is planting seeds on concrete — the best seed in the world cannot overcome an inhospitable surface.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What are Mathon's three criteria for evaluating a loan?", "answer": "Purpose (does it produce income?), ability to repay (reliable income or assets?), and character (history of fulfilling obligations?)."},
                    {"question": "What is the seventh cure and why is it often overlooked?", "answer": "Cultivate thy own powers — invest in skill, knowledge, and earning capacity. Overlooked because it yields no immediate financial return, but over a lifetime it raises the income that all other savings and investments depend upon."},
                ]},
            },
        },
    ],
})

# ─── AS A MAN THINKETH ────────────────────────────────────────────────────────
AS_A_MAN_THINKETH.update({
    "title": "As a Man Thinketh",
    "author": "James Allen",
    "category": "Philosophy & Self-Help",
    "total_pages": 72,
    "readers_count": 2_000_000,
    "rating": 4.5,
    "cover_image_url": "https://m.media-amazon.com/images/I/61TM8LDQJYL._AC_UY218_.jpg",
    "is_recommended": False, "is_trending": True,
    "reading_mode": "skim", "daily_minutes": 15,
    "book_type": "philosophy", "complexity_level": "beginner", "badge": "CLASSIC",
    "description": "Written in 1903, this short masterpiece explores the relationship between thought and character, circumstances, health, and purpose. Allen's central insight: a person is literally what they think.",
    "book_brief": {
        "what": "A 72-page masterpiece on the relationship between thought, character, and life circumstances — written in 1903.",
        "who": "Anyone who wants to understand the direct connection between their habitual thinking and the quality of their life.",
        "core_argument": "A person is literally what they think. Character is the garden; thought is the seed; circumstance is the harvest.",
        "top_5_ideas": [
            "Thought is the foundation of all character — what you habitually think, you become.",
            "Circumstances are the outward expression of inward thought — not the cause of your situation but its reflection.",
            "A noble purpose acts as a compass, directing all thought and action with natural coherence.",
            "Mental and physical health are directly connected to the quality of habitual thought.",
            "Achievement is the natural result of directed, purposeful thought — not luck or circumstance.",
        ],
        "verdict": "Read in 90 minutes. One of the most concise and profound books ever written. Re-read annually.",
    },
    "flashcards": [
        {"q": "What is Allen's central thesis in As a Man Thinketh?", "a": "A person is literally what they think. Character, circumstances, health, and achievement are all direct expressions of habitual thought patterns."},
        {"q": "What is Allen's garden metaphor?", "a": "The mind is a garden — it can be cultivated or allowed to run wild. Plant positive, purposeful thoughts and they yield a life of character and achievement. Leave it untended and weeds (negative thought) take over."},
        {"q": "What does Allen say about circumstances?", "a": "Circumstances do not make a person — they reveal a person. Your circumstances are the outward expression of your inward thought, not an external force acting upon you."},
        {"q": "What role does purpose play in Allen's philosophy?", "a": "A definite purpose acts as a compass for all thought and action. Without purpose, thought is scattered and achievement impossible. With it, all energy naturally aligns."},
        {"q": "What is Allen's teaching on health and thought?", "a": "The body is the servant of the mind. Fearful and impure thoughts produce disease and weakness. Clean, courageous, and serene thoughts produce physical health and vitality."},
    ],
    "chapters": [
        {
            "number": 1, "title": "Thought and Character",
            "page_start": 1, "page_end": 20, "duration_minutes": 18,
            "hook": "A man is literally what he thinks, his character being the complete sum of all his thoughts.",
            "chunks": [
                {"index": 1, "day": 1, "text": (
                    "James Allen opens with the most direct statement in the history of self-help literature: "
                    "*'A man is literally what he thinks, his character being the complete sum of all his thoughts.'*\n\n"
                    "He is not speaking metaphorically. He means this precisely: the patterns of your thought "
                    "are what you are. Not what you say, not what you aspire to be, not what you were born as — "
                    "but what you habitually, consistently, privately think.\n\n"
                    "His evidence is the mind-as-garden metaphor. A garden left untended does not produce nothing — "
                    "it produces weeds. A mind left untended does not produce neutral content — it produces "
                    "the doubts, fears, resentments, and petty concerns that accumulate when no deliberate cultivation occurs.\n\n"
                    "But a garden deliberately cultivated — cleared, seeded, and tended — produces exactly the "
                    "plants the gardener intended. So too the mind: deliberately seeded with purposeful, "
                    "courageous, compassionate thoughts, it produces character of corresponding quality. "
                    "The gardener who complains about weeds while doing no weeding is Allen's image of the person "
                    "who blames their character on their circumstances."
                )},
                {"index": 2, "day": 2, "text": (
                    "Allen makes his most controversial claim in the chapter on circumstances:\n\n"
                    "*'Circumstances do not make the man — they reveal him.'*\n\n"
                    "This is not victim-blaming. Allen is not saying that difficult circumstances are deserved "
                    "or that people in poverty lack virtue. He is saying something more precise: "
                    "the way a person responds to circumstances — and over time, the circumstances they attract and create — "
                    "is the outward expression of their inward thought.\n\n"
                    "He notes that people are not disturbed by events but by their thoughts about events — "
                    "a claim that anticipates Stoic philosophy and modern cognitive-behavioural therapy by centuries.\n\n"
                    "The practical implication: if you want your circumstances to change, begin with your thoughts. "
                    "Not because positive thinking magically rearranges the world, but because thought determines action, "
                    "and action determines circumstances. The chain is: habitual thought → character → action → circumstance.\n\n"
                    "Change the first link and all others follow."
                )},
            ],
            "summary": {
                "title": "Thought and Character: The Complete Sum",
                "content": "Character is the complete sum of habitual thought. The mind-as-garden metaphor: untended minds produce weeds; deliberately cultivated minds produce character of corresponding quality. Circumstances reveal character rather than making it — the chain is thought → character → action → circumstance.",
                "key_takeaways": ["A person is literally what they habitually think.", "The mind is a garden — untended, it produces weeds; deliberately cultivated, it produces intended character.", "Circumstances reveal character, they don't create it.", "Change habitual thought and all subsequent links in the chain (character, action, circumstance) follow."],
            },
            "intelligence": {
                "skim": {"one_liner": "A person is literally what they habitually think — character is the sum of all thoughts; circumstances reveal character rather than making it."},
                "concept": {"concepts": [
                    {"name": "Mind as Garden", "description": "The mind untended produces weeds (doubt, fear, resentment); deliberately seeded with purposeful thought, it produces character of corresponding quality."},
                    {"name": "Thought-Character-Circumstance Chain", "description": "Habitual thought → character → action → circumstance. Change the first link and all others follow."},
                    {"name": "Circumstances as Revelation", "description": "Circumstances don't make a person — they reveal them. The outward life is the expression of inward thought."},
                ]},
                "deep": {
                    "breakdown": "Allen's thought-character chain anticipates CBT's cognitive model by 60 years: thoughts → feelings → behaviours → consequences. His insistence that circumstances reveal rather than make character maps to Epictetus's dichotomy of control: focus on what is yours (thought, response) not what is not yours (external events).",
                    "examples": ["Two people facing the same business failure: one catastrophises and contracts; the other examines, learns, and rebuilds — same circumstance, different character revealing different habitual thought.", "Allen himself: born into poverty, largely self-educated, became one of the most widely read philosophical writers of the 20th century through deliberate cultivation of thought."],
                    "analogy": "Thought is like a compass — it doesn't move your feet, but it determines every direction you take. Change the compass and you change the destination.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is Allen's central claim about thought and character?", "answer": "A person is literally what they habitually think — character is the complete sum of all thoughts. Deliberately cultivated thought produces character of corresponding quality."},
                    {"question": "What does Allen mean by 'circumstances don't make the man — they reveal him'?", "answer": "Circumstances are the outward expression of inward thought. The chain is habitual thought → character → action → circumstance. Change the thought and eventually the circumstance follows."},
                ]},
            },
        },
        {
            "number": 2, "title": "Effect of Thought on Purpose and Achievement",
            "page_start": 21, "page_end": 50, "duration_minutes": 20,
            "hook": "Until thought is linked to purpose, there is no intelligent accomplishment. Thought energy scattered in all directions produces nothing.",
            "chunks": [
                {"index": 3, "day": 3, "text": (
                    "Allen's chapter on purpose is the most practical in the book.\n\n"
                    "He argues that until thought is linked to purpose, there is no intelligent accomplishment. "
                    "The person who drifts through life — responding reactively to circumstances, pursuing whatever "
                    "is pleasurable or avoiding whatever is uncomfortable — is scattering their thought-energy "
                    "in all directions. Scattered energy produces scattered results.\n\n"
                    "He makes a sharp distinction between vague wishes and definite purpose. "
                    "A wish is passive — it asks the world to deliver. "
                    "A definite purpose acts as a compass, giving direction to all thought and action. "
                    "Once purpose is established, all the mental energy previously scattered in anxiety, distraction, "
                    "and idle fantasy naturally aligns behind it.\n\n"
                    "He identifies the practical method: **choose a purpose that genuinely aligns with your deepest values "
                    "and highest conception of yourself**, not one chosen for external approval or financial incentive alone. "
                    "A purpose held with genuine conviction generates the kind of thought that produces creative solutions, "
                    "persistent effort, and the quality of work that others recognise as exceptional."
                )},
                {"index": 4, "day": 4, "text": (
                    "Allen closes the book with his most challenging teaching — one that most readers prefer not to hear:\n\n"
                    "*'Men are anxious to improve their circumstances, but are unwilling to improve themselves; "
                    "they therefore remain bound.'*\n\n"
                    "He is not harsh about this. He acknowledges that self-improvement is genuinely difficult "
                    "and that the habit of blaming external circumstances for internal conditions is deeply entrenched. "
                    "But he insists that no amount of external change — better job, better relationships, better city — "
                    "will produce lasting improvement in a life until the thought-patterns that generated "
                    "the original conditions are themselves changed.\n\n"
                    "His final words are among the most quoted in the history of motivational literature:\n\n"
                    "*'Dream lofty dreams, and as you dream, so shall you become. "
                    "Your vision is the promise of what you shall one day be. "
                    "Your ideal is the prophecy of what you shall at last unveil.'*\n\n"
                    "This is not mysticism. It is observation: the quality of the life a person eventually lives "
                    "rarely exceeds the quality of the vision they habitually hold."
                )},
            ],
            "summary": {
                "title": "Purpose: The Compass That Aligns All Thought",
                "content": "Without purpose, thought is scattered and achievement impossible. A definite purpose aligns all mental energy behind a single direction. Most people want better circumstances without improving themselves — but lasting circumstantial improvement requires the prior improvement of thought. Dream lofty dreams; the quality of your eventual life rarely exceeds the quality of your habitual vision.",
                "key_takeaways": ["Until thought is linked to purpose, there is no intelligent accomplishment.", "A definite purpose aligns scattered thought-energy behind a single direction.", "External circumstances cannot improve permanently without prior improvement of thought.", "Dream lofty dreams — the quality of life rarely exceeds the quality of habitual vision."],
            },
            "intelligence": {
                "skim": {"one_liner": "Link thought to definite purpose — scattered thought-energy produces nothing; your habitual vision is the promise of what you will eventually become."},
                "concept": {"concepts": [
                    {"name": "Definite Purpose", "description": "A clear, deeply held intention that acts as a compass for all thought and action — aligning mental energy that would otherwise scatter in anxiety and distraction."},
                    {"name": "Wish vs Purpose", "description": "A wish is passive (asking the world to deliver). A purpose is active (directing all thought and action toward a specific, valued outcome)."},
                    {"name": "Habitual Vision", "description": "The quality of the life a person eventually lives rarely exceeds the quality of the vision they habitually hold — dream loftily and specifically."},
                ]},
                "deep": {
                    "breakdown": "Allen's 'purpose as compass' maps to modern research on implementation intentions — the finding that specific, concrete intentions (when/where/how) produce dramatically higher follow-through than vague goals. The 'improve yourself before expecting circumstances to improve' teaching maps to Victor Frankl: you cannot change external conditions by remaining the same person who created them.",
                    "examples": ["Two people with equal talent: one with definite purpose and one drifting. Within 10 years, the gap in achievement is not a function of talent but of directed vs scattered thought.", "Allen himself: wrote As a Man Thinketh not for financial reward but as genuine expression of purpose — it outlasted him by over a century."],
                    "analogy": "Purpose is a magnifying glass held over the scattered sunlight of thought. Without it, the light warms vaguely. With it, it can start a fire.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is the role of purpose in Allen's framework?", "answer": "A definite purpose acts as a compass for all thought and action, aligning the mental energy that would otherwise scatter in anxiety and distraction. Without purpose, there is no intelligent accomplishment."},
                    {"question": "What does Allen mean by 'men are anxious to improve circumstances but unwilling to improve themselves'?", "answer": "External circumstances are expressions of inward thought. Until the thought-patterns that generated the original conditions change, no external improvement is lasting. Self-improvement (thought improvement) must precede circumstantial improvement."},
                ]},
            },
        },
        {
            "number": 3, "title": "Thought, Health, and Serenity",
            "page_start": 51, "page_end": 72, "duration_minutes": 15,
            "hook": "The body is the servant of the mind. It obeys the operations of the mind, whether they be deliberately chosen or automatically expressed.",
            "chunks": [
                {"index": 5, "day": 5, "text": (
                    "Allen's chapter on health is the most radical in the book and the most contemporary in its implications:\n\n"
                    "*'The body is the servant of the mind. It obeys the operations of the mind, "
                    "whether they be deliberately chosen or automatically expressed.'*\n\n"
                    "He argues that fearful and impure thoughts — chronic anxiety, resentment, self-loathing — "
                    "express themselves in the body as disease, weakness, and premature aging. "
                    "This was controversial in 1903 and has since been confirmed by decades of psychoneuroimmunology: "
                    "chronic stress hormones suppress immune function, accelerate cellular aging, and contribute "
                    "to cardiovascular disease.\n\n"
                    "Conversely, clean, courageous, and serene thoughts — habitual equanimity, gratitude, "
                    "and genuine goodwill toward others — express themselves as physical vitality, clear eyes, "
                    "and the quality of presence that people describe as 'health from the inside out.'\n\n"
                    "Allen does not claim that thought can cure all illness. But he insists that the quality of "
                    "habitual thought is the single most controllable variable in physical health."
                )},
                {"index": 6, "day": 6, "text": (
                    "Allen closes with his teaching on serenity — the highest expression of mental development.\n\n"
                    "*'Calmness of mind is one of the beautiful jewels of wisdom. It is the result of long and patient effort in "
                    "self-control. Its presence is an indication of ripened experience, and of a more than ordinary "
                    "knowledge of the laws and operations of thought.'*\n\n"
                    "Serenity is not passivity. It is not indifference. It is the state of a person who has so thoroughly "
                    "understood and managed their own thought-patterns that they are no longer at the mercy of "
                    "every external disturbance. Events may be turbulent. The mind remains still.\n\n"
                    "He notes that such people are immediately recognisable: they have a quality of presence "
                    "that others find calming and authoritative. Their words carry weight because they are "
                    "spoken from a stable centre, not from reaction. Their decisions are sound because they are "
                    "made without distortion by fear or anger.\n\n"
                    "Serenity, Allen concludes, is not the absence of difficulty. It is the presence of a mind "
                    "that difficulty cannot overwhelm."
                )},
            ],
            "summary": {
                "title": "Thought, Health, and Serenity: The Complete Expression",
                "content": "The body is the servant of the mind — habitual thought patterns express themselves directly in physical health. Serenity is the highest expression of mental development: not passivity but the state of a person whose thought-patterns are so well managed that external disturbance cannot overwhelm them. It is recognisable, teachable, and the natural result of long self-discipline.",
                "key_takeaways": ["The body is the servant of the mind — habitual thought directly affects physical health.", "Fearful/anxious thought produces disease; serene/courageous thought produces vitality.", "Serenity is the highest expression of wisdom — not passive, but unshakeable.", "Serenity is not the absence of difficulty but the presence of a mind that difficulty cannot overwhelm."],
            },
            "intelligence": {
                "skim": {"one_liner": "The body serves the mind — habitual thought directly shapes physical health; serenity is the highest wisdom, the state where external difficulty can no longer overwhelm the well-disciplined mind."},
                "concept": {"concepts": [
                    {"name": "Mind-Body Connection", "description": "Habitual thought patterns express themselves in physical health — chronic negative thought produces disease; serene, courageous thought produces vitality."},
                    {"name": "Serenity as Wisdom", "description": "The highest expression of mental development — not passivity but unshakeable stability, the result of long self-discipline in thought management."},
                    {"name": "Presence as Authority", "description": "The serene person speaks from a stable centre — words carry weight, decisions avoid fear and anger distortion, presence is calming to others."},
                ]},
                "deep": {
                    "breakdown": "Allen's mind-body chapter anticipates psychoneuroimmunology by 70 years. Modern research confirms: chronic stress hormones (cortisol, adrenaline) suppress immune function, accelerate cellular aging, and contribute to cardiovascular disease. Allen's prescribed remedy — cultivated serenity through deliberate thought management — maps to modern mindfulness-based stress reduction (MBSR).",
                    "examples": ["Medical studies on chronic anxiety patients showing accelerated biological aging (telomere shortening) vs meditation practitioners showing slowed aging.", "The 'presence' of serene leaders — consistently described by subordinates as calming and authoritative."],
                    "analogy": "Serenity is a deep harbour. The surface may be rough with weather (circumstances), but the depths remain still — and it is from those depths that ships navigate safely.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What does Allen mean by 'the body is the servant of the mind'?", "answer": "Habitual thought patterns express themselves directly in physical health. Fearful/anxious thought produces disease and weakness; serene/courageous thought produces vitality."},
                    {"question": "What is Allen's definition of serenity?", "answer": "The highest expression of mental development — not passivity or indifference but the state of a person whose thought-patterns are so well managed that external disturbance can no longer overwhelm them. The result of long, patient self-discipline."},
                ]},
            },
        },
    ],
})

# ─── LETTERS FROM A STOIC ─────────────────────────────────────────────────────
LETTERS_STOIC.update({
    "title": "Letters from a Stoic",
    "author": "Seneca",
    "category": "Philosophy",
    "total_pages": 271,
    "readers_count": 1_500_000,
    "rating": 4.7,
    "cover_image_url": "https://m.media-amazon.com/images/I/71KqszlN8bL._AC_UY218_.jpg",
    "is_recommended": False, "is_trending": False,
    "reading_mode": "deep", "daily_minutes": 25,
    "book_type": "philosophy", "complexity_level": "intermediate", "badge": "TIMELESS",
    "description": "A selection of Seneca's letters to his friend Lucilius, written in the final years of his life. These letters cover time, friendship, death, virtue, and the art of living well — and remain among the most readable works of Stoic philosophy.",
    "book_brief": {
        "what": "Selected letters from Roman statesman Seneca to his friend Lucilius — practical Stoic philosophy on time, death, friendship, and virtue.",
        "who": "Anyone seeking a philosophical framework for living well that is both ancient and immediately applicable.",
        "core_argument": "Time is the most precious resource — guard it. Virtue is the only true good. Death well-contemplated is the path to living well.",
        "top_5_ideas": [
            "Time is the most precious resource — and the one most freely wasted.",
            "Virtue alone is good in itself; everything else (wealth, health, status) is preferred indifferent.",
            "Contemplating death is not morbid — it is the practice that makes present life vivid.",
            "True friendship requires complete trust — but is only possible between people of good character.",
            "Philosophy is not an ornament of the wealthy — it is the practical art of living well for anyone.",
        ],
        "verdict": "Seneca writes like a wise friend talking directly to you. Underline everything. Return annually.",
    },
    "flashcards": [
        {"q": "What does Seneca say about time in Letter I?", "a": "Reclaim and save time — it is the most precious resource and the one most freely given away. We guard money, property, and possessions, but allow our time to be seized, wasted, and stolen without protest."},
        {"q": "What is the Stoic definition of the good?", "a": "Only virtue is genuinely good. Everything else — wealth, health, status, pleasure — is 'preferred indifferent': desirable but not necessary for eudaimonia (flourishing)."},
        {"q": "What does Seneca say about the contemplation of death?", "a": "Meditatio mortis — daily contemplation of death — is the practice that makes present life vivid. 'Let us prepare our minds as if we had come to the very end of life. Let us postpone nothing.'"},
        {"q": "What does Seneca require of true friendship?", "a": "Complete trust and shared good character. You cannot trust someone completely unless you have first judged their character thoroughly. But once you have, trust completely — partial friendship is no friendship."},
        {"q": "What is Seneca's counsel on philosophy?", "a": "Philosophy is not an ornament or display — it is medicine for the soul. Study it to live better, not to appear learned. 'Show me that you have stopped running away from yourself.'"},
    ],
    "chapters": [
        {
            "number": 1, "title": "On Saving Time — The Most Precious Resource",
            "page_start": 1, "page_end": 45, "duration_minutes": 28,
            "hook": "Ita fac, mi Lucili: vindica te tibi. — Do this, my Lucilius: claim yourself for yourself.",
            "chunks": [
                {"index": 1, "day": 1, "text": (
                    "Seneca opens his letters with the most urgent instruction he has to give:\n\n"
                    "*'Ita fac, mi Lucili: vindica te tibi.'* — Do this, my Lucilius: claim yourself for yourself.\n\n"
                    "He then makes his case for why this instruction is so urgent. "
                    "Time, he argues, is the only resource that cannot be recovered once given away. "
                    "Gold lost can be earned again. Reputation damaged can be restored. "
                    "Health broken can sometimes be rebuilt. But an hour spent — spent on anything — is gone permanently.\n\n"
                    "What disturbs him most is not that people waste time, but that they do so *voluntarily and cheerfully.* "
                    "They guard their money with contracts and lawyers. They protect their property with locks and guards. "
                    "But they allow their days — their *actual life* — to be seized by anyone who wants a piece of it: "
                    "trivial social obligations, the petty demands of ambition, the endless consumption of news and gossip.\n\n"
                    "He writes: *'No man is so busy that he cannot sometimes steal an hour.'* "
                    "The question is not whether you have time — you do. The question is whether you are willing to reclaim it."
                )},
                {"index": 2, "day": 2, "text": (
                    "Seneca turns to the relationship between time-wasting and the fear of death — "
                    "an analysis that feels contemporary despite its two thousand years.\n\n"
                    "He observes that most people avoid thinking about death precisely because doing so would force them "
                    "to evaluate how they are actually spending their days. If you knew you had six months left to live, "
                    "how would you spend them? Almost certainly differently from how you spend them now. "
                    "But that calculation changes nothing about reality — you have exactly the same limited time regardless.\n\n"
                    "*'Omnia, Lucili, aliena sunt, tempus tantum nostrum est.'* "
                    "— Everything, Lucilius, belongs to others; time alone is ours.\n\n"
                    "His practical instruction: gather and save time, not by abandoning all social obligation, "
                    "but by becoming ruthlessly deliberate about what you give your hours to. "
                    "Distinguish between what you *choose* to spend time on and what you allow to *seize* your time. "
                    "The first is a free person's use of life. The second is slow enslavement."
                )},
            ],
            "summary": {
                "title": "On Saving Time",
                "content": "Time is the only resource that cannot be recovered. We guard possessions with care but allow our actual life to be seized by trivial obligations, social demands, and passive distraction. Seneca's instruction: claim yourself for yourself — become deliberately selective about what you give your hours to.",
                "key_takeaways": ["Time is the only resource that cannot be recovered — guard it more jealously than money.", "Most people allow their days to be seized voluntarily and cheerfully.", "Everything belongs to others; time alone is ours.", "Distinguish choosing to spend time from allowing it to be taken."],
            },
            "intelligence": {
                "skim": {"one_liner": "Time is the only irreplaceable resource — claim yourself for yourself; stop allowing your hours to be seized voluntarily while you guard money with contracts."},
                "concept": {"concepts": [
                    {"name": "Vindica te tibi", "description": "Claim yourself for yourself — the foundational Stoic instruction to reclaim time from the trivial demands of ambition, social obligation, and distraction."},
                    {"name": "Irreversibility of Time", "description": "Unlike money, reputation, or health, time lost cannot be recovered. This single fact should govern all allocation decisions."},
                    {"name": "Deliberate Time Allocation", "description": "Distinguish choosing to spend time (free person) from allowing it to be seized (slow enslavement). The same hours; entirely different relationship to them."},
                ]},
                "deep": {
                    "breakdown": "Seneca's time analysis anticipates modern concepts of attention economics (Herbert Simon) and time affluence research (positive psychology). The distinction between chosen and seized time maps directly to Csikszentmihalyi's autotelic experience vs reactive consumption.",
                    "examples": ["A person who says 'I have no time' but watches 3 hours of television daily is not time-poor — they are time-unguarded.", "The executive who clears Monday mornings for deep work is practising Seneca's time reclamation 2,000 years later."],
                    "analogy": "Time is like water in cupped hands. You didn't choose the amount you have. But you can choose whether to cup them tightly and drink deeply, or let it drain through your fingers on the way to something else.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is Seneca's central teaching in Letter I?", "answer": "Claim yourself for yourself (vindica te tibi). Time is the only irreplaceable resource — guard it more jealously than money. Distinguish choosing to spend time from allowing it to be seized."},
                    {"question": "Why does Seneca connect time-wasting to avoidance of death?", "answer": "Contemplating death forces an honest evaluation of how time is actually spent. Most people avoid this calculation precisely because it would reveal how much of their actual life is being given away involuntarily."},
                ]},
            },
        },
        {
            "number": 2, "title": "On Friendship — Trust and Character",
            "page_start": 46, "page_end": 110, "duration_minutes": 30,
            "hook": "Before you trust someone completely, judge them. But once you have judged, trust completely — partial friendship is no friendship at all.",
            "chunks": [
                {"index": 3, "day": 3, "text": (
                    "Seneca writes one of the most practically useful letters in the collection on the subject of friendship — "
                    "and begins with what sounds like a paradox:\n\n"
                    "*'Hoc primum philosophia promittit: sensum communem, humanitatem et congregationem.'* "
                    "— Philosophy's first promise is common sense, humanity, and fellowship.\n\n"
                    "He identifies two equal and opposite errors in how people approach friendship. "
                    "The first: trusting everyone immediately, sharing thoughts and secrets before a person's "
                    "character has been tested. This produces betrayal and the gradual withdrawal from all intimacy.\n\n"
                    "The second, and in his view more common error: trusting no one, keeping all relationships "
                    "at arm's length because some people have proved untrustworthy. "
                    "This produces the existential isolation that he considers the greatest human poverty.\n\n"
                    "His prescription: judge carefully before you trust. But *once you have judged*, trust without reservation. "
                    "A friend you must constantly guard yourself against is not a friend — they are an acquaintance "
                    "who happens to be nearby. True friendship requires you to be able to say everything to them "
                    "that you can say to yourself."
                )},
                {"index": 4, "day": 4, "text": (
                    "Seneca makes one of his most challenging observations in the friendship letters:\n\n"
                    "True friendship is only possible between people who are both genuinely trying to become better. "
                    "Not perfect — Seneca is explicit that he himself is deeply imperfect and in active progress. "
                    "But moving in the right direction, with honest self-examination, not rationalising away failures.\n\n"
                    "He notes that the most common substitute for friendship is *utility* — keeping relationships "
                    "for what they can provide: access, information, pleasure, status. These relationships are real "
                    "and have their place, but they do not constitute friendship. They are dissolved the moment "
                    "the utility disappears.\n\n"
                    "Genuine friendship, by contrast, is sought for its own sake. The friend is valued not for "
                    "what they provide but for who they are. And when someone is valued for who they are, "
                    "the relationship survives the loss of everything external.\n\n"
                    "*'Dum differtur vita transcurrit.'* — While we delay, life passes. "
                    "Do not defer the cultivation of genuine friendship to a less busy season. "
                    "The busy season never ends."
                )},
            ],
            "summary": {
                "title": "On Friendship: Complete Trust Requires Good Character",
                "content": "True friendship requires thorough prior judgment of character followed by complete trust — partial trust is not friendship. The most common substitute for friendship is utility, which dissolves when the utility disappears. Genuine friendship is sought for its own sake and survives all external losses.",
                "key_takeaways": ["Judge carefully before trusting; then trust completely.", "Partial friendship is no friendship — it is acquaintance.", "Most relationships are based on utility, not genuine friendship.", "Do not defer friendship cultivation — the busy season never ends."],
            },
            "intelligence": {
                "skim": {"one_liner": "Judge character carefully before trusting; then trust completely — partial trust is not friendship; genuine friendship is sought for its own sake, not for utility."},
                "concept": {"concepts": [
                    {"name": "Two Errors of Friendship", "description": "Trusting too quickly (produces betrayal) and trusting no one (produces isolation). Seneca's middle path: thorough prior judgment, then complete trust."},
                    {"name": "Friendship vs Utility", "description": "Utility-based relationships dissolve when the utility disappears. Genuine friendship values the person for who they are and survives all external losses."},
                    {"name": "Character as Prerequisite", "description": "True friendship is only possible between people both genuinely trying to become better — not perfect, but moving in the right direction with honest self-examination."},
                ]},
                "deep": {
                    "breakdown": "Seneca's friendship philosophy anticipates Aristotle's three types of friendship (utility, pleasure, virtue) and confirms the empirical finding that virtue-friendship is the only type that produces lasting well-being. Modern attachment theory confirms: secure attachment requires both discernment (don't trust everyone indiscriminately) and openness (don't close off because of past betrayal).",
                    "examples": ["A colleague who is warm and helpful but whose behaviour changes when there is nothing to gain — utility friendship in action.", "A friend who has known you through failure and success and whose counsel you trust precisely because they have no agenda — genuine friendship."],
                    "analogy": "Friendship is like a garden. You can't open it to every visitor — most will trample it. But you also can't lock it against everyone — then nothing grows. The art is in choosing carefully who to let in.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What are Seneca's two equal errors in friendship?", "answer": "Trusting everyone immediately (produces betrayal, eventual withdrawal from intimacy) and trusting no one (produces isolation). The correct path: judge thoroughly first, then trust completely."},
                    {"question": "What distinguishes true friendship from utility-based relationships in Seneca?", "answer": "True friendship is sought for the person's own sake and survives all external losses. Utility-based relationships are dissolved the moment the utility disappears — they are acquaintance, not friendship."},
                ]},
            },
        },
        {
            "number": 3, "title": "On the Shortness of Life and the Art of Dying Well",
            "page_start": 111, "page_end": 271, "duration_minutes": 35,
            "hook": "Non differtur vita transcurrit. — Life is not postponed, it passes.",
            "chunks": [
                {"index": 5, "day": 5, "text": (
                    "Seneca returns again and again, across all his letters, to the theme of death — "
                    "not because he is morbid, but because he is convinced that nothing clarifies life as sharply.\n\n"
                    "*'Cogita quantum temporis absumpserit, quantum rapuerit morbus, quantum somnus, quantum labor cotidianus.'* "
                    "— Think how much time illness has consumed, how much sleep, how much daily toil.\n\n"
                    "His practice — which he recommends to Lucilius with great earnestness — is *meditatio mortis*: "
                    "the daily contemplation of death. Not as self-torture or nihilism, but as a clarifying lens. "
                    "When you clearly see that today may be your last, you are forced to evaluate whether "
                    "the way you are spending it is the way you would choose to spend your last day.\n\n"
                    "He notes that most people postpone their actual lives: *'When I have made enough money, then I will begin to live. "
                    "When the children are grown, when the project is complete, when the storm passes.'* "
                    "But this postponement is not waiting for life to begin — it is life passing while you wait.\n\n"
                    "*'Omnia, Lucili, aliena sunt, tempus tantum nostrum est.'* "
                    "Everything belongs to others; time alone is ours. And it is running."
                )},
                {"index": 6, "day": 6, "text": (
                    "Seneca's final letters address the quality of the philosopher's mind in the face of death — "
                    "and produce some of the most beautiful prose in classical literature.\n\n"
                    "He writes to Lucilius about his own declining health without self-pity and without pretence:\n\n"
                    "*'Ita fac, mi Lucili: asserva te philosophiae. Non ad hoc ut philosophiae praesidio uti possis, "
                    "sed ut philosophia praesidio tuo.'* — Devote yourself to philosophy. Not that you may use it "
                    "for protection, but that it may use your protection.\n\n"
                    "The Stoic sage does not merely endure death — they approach it with equanimity born not of "
                    "indifference but of genuine understanding. They have lived; they have contributed; "
                    "they have loved and been loved. The account is not in deficit.\n\n"
                    "His final counsel is the simplest and most demanding: *live as though you are always "
                    "at the end.* Not in resignation — in full presence. Every conversation as if it may be the last. "
                    "Every friendship tended as if time is short, because it is. Every hour claimed for yourself, "
                    "because no one else will claim it for you.\n\n"
                    "These letters, written by a man who knew he was dying and who wrote anyway, "
                    "are among the most life-affirming documents in human history."
                )},
            ],
            "summary": {
                "title": "On Death and Living Fully",
                "content": "Daily contemplation of death (meditatio mortis) is not morbid — it is the practice that makes present life vivid. Most people postpone their actual lives, waiting for conditions to be right. But life is not postponed — it passes. The Stoic counsel: live as though always at the end — in full presence, with every friendship tended and every hour claimed.",
                "key_takeaways": ["Meditatio mortis — daily contemplation of death — is life's sharpest clarifying lens.", "Most people postpone living; life is not postponed — it passes.", "Live as though always at the end — in full presence, not resignation.", "Devote yourself to philosophy not for protection but as an offering."],
            },
            "intelligence": {
                "skim": {"one_liner": "Daily contemplation of death clarifies how to live; most people postpone living while life passes — live as though always at the end, in full presence."},
                "concept": {"concepts": [
                    {"name": "Meditatio Mortis", "description": "Daily contemplation of death — not morbid, but a clarifying practice that forces honest evaluation of whether today is being spent as a last day would be."},
                    {"name": "The Postponed Life", "description": "'When X, then I will begin to live' — Seneca's diagnosis of the most common human failure. Life is not postponed; it passes."},
                    {"name": "Equanimity at the End", "description": "The Stoic sage approaches death with equanimity born of genuine understanding — having lived, contributed, loved. The account is not in deficit."},
                ]},
                "deep": {
                    "breakdown": "Seneca's meditatio mortis maps to modern Terror Management Theory (TMT) — the finding that mortality salience (awareness of death) can either produce defensive anxiety or, when processed with philosophical acceptance, profound clarity about what matters. Seneca prescribes the second path explicitly.",
                    "examples": ["Steve Jobs' Stanford commencement address: 'Remembering that I'll be dead soon is the most important tool I've ever encountered to help me make the big choices in life.'", "Seneca himself: writing letters of extraordinary clarity and warmth while knowing Nero might order his death at any moment."],
                    "analogy": "Death is the blank wall at the end of a corridor. Most people walk away from it and so can never see how short the corridor is. Seneca says: turn around, look at the wall, measure the distance — then choose your steps accordingly.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is meditatio mortis and what is its purpose?", "answer": "Daily contemplation of death — not as morbidity but as a clarifying practice that forces honest evaluation of whether today is being spent as a last day would be. Makes present life vivid rather than postponed."},
                    {"question": "What does Seneca mean by 'life is not postponed — it passes'?", "answer": "Most people delay actual living waiting for conditions to improve. But the waiting is not a pause before life — it is life itself, passing. The hour spent waiting was a real hour, not a placeholder."},
                ]},
            },
        },
    ],
})

# ─── THE SCIENCE OF GETTING RICH ──────────────────────────────────────────────
SCIENCE_RICH.update({
    "title": "The Science of Getting Rich",
    "author": "Wallace D. Wattles",
    "category": "Self-Help & Finance",
    "total_pages": 98,
    "readers_count": 1_000_000,
    "rating": 4.3,
    "cover_image_url": "https://m.media-amazon.com/images/I/71R8CXDXJVL._AC_UY218_.jpg",
    "is_recommended": False, "is_trending": False,
    "reading_mode": "concept", "daily_minutes": 20,
    "book_type": "self_help", "complexity_level": "beginner", "badge": "",
    "description": "Published in 1910, this compact book argues that getting rich is a science — a set of principles that, when applied with precision, produces wealth as reliably as chemistry produces water. The direct inspiration for 'The Secret'.",
    "book_brief": {
        "what": "A 98-page argument that wealth creation follows scientific principles — not luck, talent, or circumstance.",
        "who": "Anyone who wants a simple, non-mystical framework for creating wealth through purposeful thought and action.",
        "core_argument": "Getting rich is the result of doing things in a certain way — a way accessible to anyone with desire, vision, and purpose.",
        "top_5_ideas": [
            "Getting rich follows scientific law — anyone who does things in the certain way will get rich.",
            "The formless substance (creative intelligence) responds to thought impressed upon it with purpose.",
            "Gratitude connects you to the source of supply — ingratitude and discontent cut the connection.",
            "Act in the present with full faith — hold the vision clearly while acting with purpose today.",
            "Your wealth does not come at the expense of others — the universe is a place of abundance, not scarcity.",
        ],
        "verdict": "Read as a mindset primer before Hill or Clason. Short, focused, and surprisingly practical.",
    },
    "flashcards": [
        {"q": "What is the 'certain way' Wattles describes?", "a": "Thinking in a certain way (with clear, grateful, purposeful thought aligned to a definite vision) and acting in a certain way (taking every action available to you today with full faith and efficiency)."},
        {"q": "What does Wattles mean by 'formless substance'?", "a": "The creative intelligence or energy underlying all physical reality — which responds to thought impressed upon it with clear purpose. It is what think-and-grow-rich philosophy calls the subconscious, and what physics calls the quantum field."},
        {"q": "What is the role of gratitude in Wattles' system?", "a": "Gratitude connects you to the source of supply. Ingratitude and discontent create a disconnection that stops the flow of wealth. Regular, sincere gratitude keeps the channel open."},
        {"q": "What does Wattles say about competition?", "a": "Do not compete — create. Competition is the mindset of scarcity. Creation is the mindset of abundance. Those who get rich in the certain way do so by adding value to the world, not by taking from others."},
        {"q": "What is the role of action in Wattles' framework?", "a": "Thought without action produces nothing. You must think in the certain way AND take every action available to you today, done with the full efficiency and purpose of a person absolutely certain of success."},
    ],
    "chapters": [
        {
            "number": 1, "title": "The Right to Be Rich",
            "page_start": 1, "page_end": 28, "duration_minutes": 18,
            "hook": "Whatever may be said in praise of poverty, the fact remains that it is not possible to live a truly complete or successful life unless one is rich.",
            "chunks": [
                {"index": 1, "day": 1, "text": (
                    "Wattles opens with a provocation that would have been controversial in 1910 and remains arresting today:\n\n"
                    "*'Whatever may be said in praise of poverty, the fact remains that it is not possible to live "
                    "a truly complete or successful life unless one is rich.'*\n\n"
                    "He is not saying that money is the most important thing. He is making a more precise claim: "
                    "that in the material world, the expression of talent, love, and purpose requires resources. "
                    "The artist without materials cannot create. The healer without tools cannot heal. "
                    "The parent who cannot feed their children cannot parent at their full capacity. "
                    "Material sufficiency is not the goal — it is the *enabling condition* for the full expression of human potential.\n\n"
                    "He argues that wanting to be rich is therefore not greed — it is the desire for the conditions "
                    "necessary to become fully alive. The person who genuinely wants to develop their talents, "
                    "contribute meaningfully, and experience life fully *must* want the resources that make those things possible.\n\n"
                    "He then makes his central claim: getting rich is a *science.* "
                    "Not a mystery, not a matter of luck, not reserved for special talent or birth. "
                    "It follows laws — and those laws, understood and applied, produce wealth as reliably "
                    "as the laws of chemistry produce specific compounds."
                )},
                {"index": 2, "day": 2, "text": (
                    "Wattles identifies the single most important distinction in his entire book:\n\n"
                    "Getting rich is not the result of saving, hard work, thrift, or any particular environment. "
                    "People in identical circumstances, with identical resources, identical intelligence, working equally hard — "
                    "some get rich and most don't. The variable is not external.\n\n"
                    "*'The distinction between men who get rich and men who do not get rich is a mental one.'*\n\n"
                    "But he is careful to clarify that this does not mean mere positive thinking or visualisation. "
                    "The certain way is both mental AND physical — a specific quality of thought combined with "
                    "a specific quality of action. Neither alone is sufficient.\n\n"
                    "The mental component: holding a clear, grateful, purposeful vision of what you want to create, "
                    "with absolute faith that you will create it.\n\n"
                    "The physical component: taking every action available to you today with the full efficiency "
                    "and focus of a person who is absolutely certain of success — not waiting for conditions to be perfect "
                    "but acting on what is available now, completely."
                )},
            ],
            "summary": {
                "title": "The Right to Be Rich: Wealth as Enabling Condition",
                "content": "Wanting to be rich is not greed — it is the desire for the enabling conditions of full human expression. Getting rich follows scientific law: a specific quality of thought (clear, grateful, purposeful vision with absolute faith) combined with a specific quality of action (taking every available action with full efficiency today).",
                "key_takeaways": ["Wanting to be rich is the desire for the conditions necessary for full human expression.", "Getting rich follows scientific law — accessible to anyone who applies it.", "The variable between those who get rich and those who don't is mental, not circumstantial.", "The certain way requires both clear vision AND immediate, efficient action — neither alone is sufficient."],
            },
            "intelligence": {
                "skim": {"one_liner": "Getting rich is a science — a specific quality of grateful, purposeful thought combined with immediate efficient action; the variable between those who get rich and those who don't is mental."},
                "concept": {"concepts": [
                    {"name": "Wealth as Enabling Condition", "description": "Material sufficiency enables the full expression of talent, love, and purpose — wanting it is not greed but the desire to become fully alive."},
                    {"name": "The Certain Way", "description": "Clear, grateful, purposeful vision with absolute faith (mental) + taking every available action today with full efficiency (physical). Both are necessary; neither is sufficient alone."},
                    {"name": "Scientific Law of Wealth", "description": "Getting rich follows reproducible laws: those who apply them in the certain way produce wealth as reliably as chemistry produces specific compounds."},
                ]},
                "deep": {
                    "breakdown": "Wattles' 'certain way' anticipates the distinction in modern performance psychology between outcome goals (what you want) and process goals (how you act each day). His mental component maps to Hill's burning desire + faith; his action component maps to what sports psychologists call 'process focus' — acting with full commitment in the present regardless of current outcomes.",
                    "examples": ["Two farmers with identical land, identical seeds, identical weather: one acts with full efficiency and trust; one acts tentatively, distracted by doubt. Within five years, the difference is visible.", "Wattles himself: wrote this book in poverty, applying its principles, and achieved financial security before his death."],
                    "analogy": "The certain way is like tuning a radio: you need to be on exactly the right frequency (clear vision + faith) AND turn up the volume (full efficient action today). Off frequency, the volume means nothing. Low volume, the signal is lost.",
                },
                "exam": {"qa_pairs": [
                    {"question": "Why does Wattles say wanting to be rich is not greed?", "answer": "Material sufficiency is the enabling condition for the full expression of human potential — talent, love, and purpose all require resources for their fullest expression. Wanting what enables you to become fully alive is not greed."},
                    {"question": "What is the 'certain way' in Wattles' framework?", "answer": "A clear, grateful, purposeful vision held with absolute faith (mental) combined with taking every available action today with full efficiency and commitment (physical). Both are necessary; neither is sufficient alone."},
                ]},
            },
        },
        {
            "number": 2, "title": "The Certain Way — Thought, Gratitude, and Action",
            "page_start": 29, "page_end": 65, "duration_minutes": 22,
            "hook": "You must pass from the competitive to the creative mind. Creation, not competition, is the path of the person who does things in the certain way.",
            "chunks": [
                {"index": 3, "day": 3, "text": (
                    "Wattles' most practically useful chapter introduces the distinction "
                    "between the competitive mind and the creative mind:\n\n"
                    "The competitive mind operates from scarcity — the belief that there is a finite amount of wealth, "
                    "and that getting more requires taking from others or outperforming them. "
                    "This mindset produces anxiety, resentment, and the zero-sum thinking that "
                    "limits ambition to what already exists.\n\n"
                    "The creative mind operates from abundance — the recognition that new wealth is continuously "
                    "being created in the world, and that the person who adds genuine value is not taking from "
                    "anyone but adding to the total sum. The entrepreneur who creates a new product, "
                    "the artist who creates new beauty, the teacher who creates new understanding — "
                    "all are creating something that did not exist before.\n\n"
                    "Wattles' prescription: move permanently from competitive to creative thinking. "
                    "Never compete — create. Ask not 'how do I get a larger share?' but "
                    "'what can I create that the world genuinely needs?' "
                    "The second question, pursued with clarity and action, produces wealth. "
                    "The first merely redistributes it."
                )},
                {"index": 4, "day": 4, "text": (
                    "Wattles addresses the role of gratitude with unusual specificity:\n\n"
                    "*'The grateful mind is constantly fixed upon the best; therefore it tends to become the best; "
                    "it takes the form or character of the best, and will receive the best.'*\n\n"
                    "This is not sentiment. He argues that gratitude is an active mental practice that keeps "
                    "the mind oriented toward what is already working — toward abundance — rather than "
                    "toward what is missing. The mind focused on lack attracts more lack, not through "
                    "metaphysical law but through the practical mechanics of attention: "
                    "you act on what you perceive, and perception is guided by habitual focus.\n\n"
                    "He recommends daily deliberate gratitude — not as affirmation but as genuine acknowledgment "
                    "of the real good that already exists in your life. This practice counteracts the brain's "
                    "negativity bias (which evolved to notice threats, not abundance) and keeps the creative "
                    "mind oriented toward what can be built rather than what might be lost.\n\n"
                    "Combined with clear vision and efficient action, gratitude completes the triad "
                    "of the certain way: vision (where you are going), gratitude (appreciation for where you are), "
                    "action (what you are doing today)."
                )},
            ],
            "summary": {
                "title": "The Certain Way: Creative Mind, Gratitude, and Action",
                "content": "Shift from competitive (scarcity, zero-sum) to creative (abundance, value-creation) thinking. Gratitude is an active practice that keeps the mind oriented toward abundance rather than lack. Vision + gratitude + efficient daily action = the complete formula of the certain way.",
                "key_takeaways": ["Move from competitive to creative thinking — never compete, create.", "The competitive mind redistributes wealth; the creative mind creates it.", "Gratitude keeps the mind oriented toward abundance — counteracts the negativity bias.", "Vision + gratitude + action = the complete certain way."],
            },
            "intelligence": {
                "skim": {"one_liner": "Move from competitive (scarcity/taking) to creative (abundance/creating) thinking; hold a clear vision with gratitude and take efficient action today — this is the complete certain way."},
                "concept": {"concepts": [
                    {"name": "Competitive vs Creative Mind", "description": "Competitive mind: scarcity, zero-sum, 'how do I get more?' Creative mind: abundance, value-creation, 'what can I create that the world needs?' Only the second produces genuine wealth."},
                    {"name": "Gratitude as Practice", "description": "Daily deliberate gratitude keeps the mind oriented toward abundance rather than lack — countering the negativity bias and maintaining the creative orientation."},
                    {"name": "The Triad", "description": "Vision (where you're going) + gratitude (appreciation for where you are) + efficient action (what you're doing today) = the complete formula of the certain way."},
                ]},
                "deep": {
                    "breakdown": "Wattles' competitive/creative distinction maps to Peter Thiel's 'competition is for losers' framework: companies in perfect competition have no pricing power and no profit. Companies that create new categories have both. The gratitude practice maps to positive psychology's broaden-and-build theory: positive emotions broaden cognitive scope and build creative resources.",
                    "examples": ["Apple under Jobs: never competed with existing products — created entirely new categories.", "The artist who creates genuinely new work vs the one who imitates popular trends — creative vs competitive mind in direct contrast."],
                    "analogy": "Competition is trying to carve a larger slice from an existing pie. Creation is baking a new pie. The creative mind adds to the total — the competitive mind only divides it.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What is the difference between the competitive and creative mind?", "answer": "Competitive mind operates from scarcity — getting more requires taking from others or outperforming them. Creative mind operates from abundance — new wealth is created by adding genuine value. The second produces wealth; the first redistributes it."},
                    {"question": "What is the role of gratitude in the certain way?", "answer": "Gratitude keeps the mind oriented toward abundance rather than lack, countering the negativity bias. Combined with clear vision and efficient action, it completes the triad: vision (where going) + gratitude (appreciation for now) + action (what to do today)."},
                ]},
            },
        },
        {
            "number": 3, "title": "Acting in the Certain Way",
            "page_start": 66, "page_end": 98, "duration_minutes": 20,
            "hook": "Act now. There is never any time but now, and there will never be any time but now.",
            "chunks": [
                {"index": 5, "day": 5, "text": (
                    "Wattles closes with the most practically urgent section of the book: the imperative of present action.\n\n"
                    "*'Act now. There is never any time but now, and there will never be any time but now. '* "
                    "However much you have thought, planned, and visualised — none of it produces wealth until "
                    "it is translated into action. And action must be taken now, not when conditions are more favourable, "
                    "not when you feel more confident, not when the plan is more complete.\n\n"
                    "He is specific about the quality of action required. It is not frantic activity or "
                    "anxious busyness — it is the full, calm efficiency of a person who is absolutely certain "
                    "of their outcome. They are not rushing because they are afraid of failure. "
                    "They are acting with precision because they are certain of success and want to honour "
                    "every available opportunity to move toward it.\n\n"
                    "He addresses the common objection: 'I don't have the opportunity I need.' "
                    "His answer is unsparing: present action on present opportunity reveals future opportunity. "
                    "The person who takes full advantage of today's possibilities will be given tomorrow's. "
                    "The person who waits for better circumstances before acting will wait indefinitely."
                )},
                {"index": 6, "day": 6, "text": (
                    "Wattles concludes with the synthesis of the entire book:\n\n"
                    "Getting rich is not accidental. It is not a function of circumstance, luck, or talent alone. "
                    "It is the natural result of doing things in a certain way — a way defined by clarity of vision, "
                    "depth of gratitude, and the efficiency and faith of present action.\n\n"
                    "He offers a final instruction that is simultaneously the simplest and most demanding "
                    "in the book: *'Think only of the best, work only for the best, and expect only the best.'* "
                    "Not as naive optimism — as a deliberate mental discipline that keeps all thought and action "
                    "consistently oriented toward creation rather than competition, toward abundance rather than scarcity.\n\n"
                    "He acknowledges that this is a practice, not a state achieved once. "
                    "Every day brings new opportunities to slip back into competitive thinking, into ingratitude, "
                    "into waiting for better conditions before acting. "
                    "The person who gets rich in the certain way is the person who returns to the practice "
                    "every day, without exception, until it becomes their natural mode of operating in the world."
                )},
            ],
            "summary": {
                "title": "Acting in the Certain Way: Present Action with Full Faith",
                "content": "Act now — there is never any time but now. The quality of action required is the calm, full efficiency of a person certain of success. Present action on present opportunity reveals future opportunity. The synthesis: clarity of vision + depth of gratitude + efficiency of present action = getting rich in the certain way.",
                "key_takeaways": ["Act now — present action on present opportunity reveals future opportunity.", "The quality of action is calm efficiency, not anxious busyness — the certainty of success.", "Think only of the best, work only for the best, expect only the best — daily discipline.", "Return to the practice every day; it becomes the natural mode of operating."],
            },
            "intelligence": {
                "skim": {"one_liner": "Act now with the calm efficiency of a person certain of success; present action reveals future opportunity; return to the practice of vision + gratitude + action every day until it is your natural mode."},
                "concept": {"concepts": [
                    {"name": "Present Action Imperative", "description": "There is never any time but now. Taking full advantage of today's possibilities reveals tomorrow's opportunities — waiting indefinitely produces indefinite waiting."},
                    {"name": "Quality of Action", "description": "Calm, full efficiency of a person certain of success — not frantic anxiety but purposeful precision. The difference is the inner state from which action flows."},
                    {"name": "Daily Practice", "description": "The certain way is a daily practice, not a state achieved once. Return to vision + gratitude + action every day until it becomes the natural operating mode."},
                ]},
                "deep": {
                    "breakdown": "Wattles' action doctrine maps to modern concepts of 'process orientation' in performance psychology — acting with full commitment to the present action regardless of outcomes. His 'calm efficiency of certain success' maps to what Csikszentmihalyi calls flow: full absorption in present action, free from both anxiety (about failure) and boredom (from under-challenge).",
                    "examples": ["The entrepreneur who takes every small available action toward their vision while holding faith in the larger outcome — Wattles' certain way in practice.", "Reid Hoffman's advice: 'Move fast, take decisive action — the cost of indecision is always higher than the cost of imperfect action.'"],
                    "analogy": "Acting in the certain way is like sailing: you cannot control the wind (circumstances), but you can adjust the sails (quality of action) to make use of whatever wind is available. The sailor who waits for perfect wind never leaves harbour.",
                },
                "exam": {"qa_pairs": [
                    {"question": "What does Wattles mean by 'act now — there is never any time but now'?", "answer": "Present action on present opportunity reveals future opportunity. Waiting for better conditions produces indefinite waiting. The quality required is the calm efficiency of a person certain of success — not anxious busyness."},
                    {"question": "What is the complete synthesis of getting rich in the certain way?", "answer": "Clarity of vision (clear, grateful, purposeful thought with absolute faith) + depth of gratitude (daily deliberate appreciation) + efficiency of present action (taking every available action today completely) = the natural production of wealth."},
                ]},
            },
        },
    ],
})
