"""
apps/books/admin.py

Django Admin configuration for books.

Key features:
- Upload a PDF → click "Save" → chunking starts automatically in background
- See processing status (Pending / Processing / Completed / Failed)
- View processing errors if something went wrong
- Manually trigger reprocessing
- Manage chapters/chunks/flashcards inline

HOW TO ACCESS:
    1. Run: python manage.py createsuperuser
    2. Visit: http://127.0.0.1:8000/admin/
    3. Go to Books → Add Book → upload PDF → save
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib import messages
from .models import Book, Chapter, Chunk, Summary, Flashcard, UserUploadedBook


# ── Inline Admins ─────────────────────────────────────────────────────────────

class ChunkInline(admin.TabularInline):
    """Shows chunks inside the Chapter edit page."""
    model = Chunk
    fields = ('chunk_index', 'estimated_minutes', 'text_preview')
    readonly_fields = ('text_preview',)
    extra = 0
    ordering = ('chunk_index',)

    def text_preview(self, obj):
        """Show first 100 chars of chunk text."""
        return obj.text[:100] + '...' if len(obj.text) > 100 else obj.text
    text_preview.short_description = 'Preview'


class SummaryInline(admin.StackedInline):
    """Shows summary inside the Chapter edit page."""
    model = Summary
    fields = ('title', 'summary_content', 'key_takeaways', 'is_locked')
    extra = 0


class ChapterInline(admin.TabularInline):
    """Shows chapters inside the Book edit page."""
    model = Chapter
    fields = ('chapter_number', 'title', 'page_range', 'duration_in_minutes', 'is_locked')
    extra = 0
    ordering = ('chapter_number',)
    show_change_link = True  # Click to open full chapter edit page


class FlashcardInline(admin.TabularInline):
    """Shows flashcards inside the Book edit page."""
    model = Flashcard
    fields = ('question', 'answer')
    extra = 1


# ── Book Admin ────────────────────────────────────────────────────────────────

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    """
    Main book admin.

    IMPORTANT: When you upload a PDF and save, the admin automatically
    triggers the background Celery task to process the PDF.
    Refresh the page after a minute or two to see the processing status.
    """

    # What to show in the list view
    list_display = (
        'title', 'author', 'category', 'source',
        'processing_status_badge', 'is_recommended', 'is_trending',
        'is_published', 'total_chapters', 'created_at'
    )
    list_filter = ('source', 'processing_status', 'is_recommended', 'is_trending', 'is_published', 'category')
    search_fields = ('title', 'author', 'category')
    ordering = ('-created_at',)

    # List view actions
    actions = ['trigger_reprocessing', 'mark_as_recommended', 'unmark_as_recommended']

    # Form layout
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'author', 'category', 'description'),
        }),
        ('Cover Image', {
            'fields': ('cover_image', 'cover_image_url'),
            'description': 'Upload an image file OR paste an image URL. Uploaded file takes priority.',
        }),
        ('PDF Upload', {
            'fields': ('pdf_file',),
            'description': (
                '⚡ Upload a PDF here and save. '
                'The system will automatically extract text, split it into chapters, '
                'and use Claude AI to create reading chunks, summaries, and flashcards. '
                'This happens in the background — check Processing Status after ~1-2 minutes.'
            ),
        }),
        ('Visibility', {
            'fields': ('is_published', 'is_recommended', 'is_trending', 'badge'),
        }),
        ('Book Details', {
            'fields': ('rating', 'readers_count', 'has_audio', 'read_per_day_minutes'),
            'classes': ('collapse',),
        }),
        ('Processing Status', {
            'fields': ('source', 'processing_status', 'processing_error_display'),
            'classes': ('collapse',),
            'description': 'Auto-updated by the background task. Do not edit manually.',
        }),
    )

    readonly_fields = ('processing_error_display', 'source')

    # Show chapters and flashcards below the book form
    inlines = [ChapterInline, FlashcardInline]

    def processing_status_badge(self, obj):
        """Colorful badge for processing status in list view."""
        colors = {
            'pending': '#f0ad4e',    # orange
            'processing': '#5bc0de', # blue
            'completed': '#5cb85c',  # green
            'failed': '#d9534f',     # red
        }
        color = colors.get(obj.processing_status, '#999')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
            color,
            obj.get_processing_status_display(),
        )
    processing_status_badge.short_description = 'Processing'
    processing_status_badge.allow_tags = True

    def processing_error_display(self, obj):
        """Show processing error in a red box if there is one."""
        if obj.processing_error:
            return format_html(
                '<div style="background:#fff0f0;border:1px solid #d9534f;padding:10px;border-radius:4px;color:#d9534f">{}</div>',
                obj.processing_error
            )
        return '—'
    processing_error_display.short_description = 'Processing Error'

    def save_model(self, request, obj, form, change):
        """
        Override save to trigger PDF processing after upload.

        This is called when admin clicks "Save" on the book form.
        If a new PDF was uploaded, we start the background task.
        """
        # Check if a new PDF was uploaded in this save
        pdf_changed = 'pdf_file' in form.changed_data and obj.pdf_file

        super().save_model(request, obj, form, change)

        if pdf_changed:
            # Import here to avoid circular imports
            from .tasks import process_admin_book_pdf

            # Reset processing status before starting
            obj.processing_status = Book.ProcessingStatus.PENDING
            obj.processing_error = ''
            obj.save(update_fields=['processing_status', 'processing_error'])

            # Queue the background task
            process_admin_book_pdf.delay(str(obj.id))

            self.message_user(
                request,
                f'✅ PDF upload received for "{obj.title}". '
                f'Processing started in background. '
                f'Make sure your Celery worker is running: celery -A config worker --loglevel=info',
                messages.SUCCESS,
            )

    # ── Custom Actions ────────────────────────────────────────────────────────

    @admin.action(description='🔄 Reprocess PDF with AI')
    def trigger_reprocessing(self, request, queryset):
        """Re-run AI processing for selected books. Useful if processing failed."""
        from .tasks import process_admin_book_pdf
        count = 0
        for book in queryset:
            if book.pdf_file:
                book.processing_status = Book.ProcessingStatus.PENDING
                book.processing_error = ''
                book.save(update_fields=['processing_status', 'processing_error'])
                process_admin_book_pdf.delay(str(book.id))
                count += 1
        self.message_user(request, f'Started reprocessing for {count} book(s).')

    @admin.action(description='⭐ Mark as Recommended')
    def mark_as_recommended(self, request, queryset):
        queryset.update(is_recommended=True, is_published=True)
        self.message_user(request, f'Marked {queryset.count()} book(s) as recommended.')

    @admin.action(description='✖ Remove from Recommended')
    def unmark_as_recommended(self, request, queryset):
        queryset.update(is_recommended=False)
        self.message_user(request, f'Removed {queryset.count()} book(s) from recommended.')


# ── Chapter Admin ─────────────────────────────────────────────────────────────

@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('book', 'chapter_number', 'title', 'page_range', 'duration_in_minutes', 'is_locked')
    list_filter = ('book', 'is_locked')
    search_fields = ('title', 'book__title')
    ordering = ('book', 'chapter_number')
    inlines = [ChunkInline, SummaryInline]


# ── Flashcard Admin ───────────────────────────────────────────────────────────

@admin.register(Flashcard)
class FlashcardAdmin(admin.ModelAdmin):
    list_display = ('book', 'question_preview', 'answer_preview')
    list_filter = ('book',)
    search_fields = ('question', 'answer', 'book__title')

    def question_preview(self, obj):
        return obj.question[:80] + '...' if len(obj.question) > 80 else obj.question
    question_preview.short_description = 'Question'

    def answer_preview(self, obj):
        return obj.answer[:80] + '...' if len(obj.answer) > 80 else obj.answer
    answer_preview.short_description = 'Answer'


# ── UserUploadedBook Admin ────────────────────────────────────────────────────

@admin.register(UserUploadedBook)
class UserUploadedBookAdmin(admin.ModelAdmin):
    """
    View and manage books that USERS uploaded from the Flutter app.
    Read-only — admins can monitor uploads and manually trigger reprocessing.
    """
    list_display = ('title', 'author', 'uploaded_by', 'status_badge', 'uploaded_at', 'book_link')
    list_filter = ('status', 'uploaded_at')
    search_fields = ('title', 'author', 'uploaded_by__email')
    readonly_fields = ('uploaded_by', 'title', 'author', 'pdf_file', 'status',
                       'error_message', 'book', 'uploaded_at', 'processed_at')
    ordering = ('-uploaded_at',)
    actions = ['retry_processing']

    def status_badge(self, obj):
        colors = {
            'pending': '#f0ad4e',
            'processing': '#5bc0de',
            'completed': '#5cb85c',
            'failed': '#d9534f',
        }
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'

    def book_link(self, obj):
        if obj.book:
            return format_html('<a href="/admin/books/book/{}/change/">View Book</a>', obj.book.id)
        return '—'
    book_link.short_description = 'Book'

    @admin.action(description='🔄 Retry failed processing')
    def retry_processing(self, request, queryset):
        from .tasks import process_user_uploaded_book
        count = 0
        for upload in queryset.filter(status=UserUploadedBook.Status.FAILED):
            upload.status = UserUploadedBook.Status.PENDING
            upload.error_message = ''
            upload.save(update_fields=['status', 'error_message'])
            process_user_uploaded_book.delay(str(upload.id))
            count += 1
        self.message_user(request, f'Retrying processing for {count} upload(s).')