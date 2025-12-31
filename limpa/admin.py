from django.contrib import admin

from limpa.models import Podcast


@admin.register(Podcast)
class PodcastAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "url"]
    readonly_fields = ["url_hash", "created_at"]
