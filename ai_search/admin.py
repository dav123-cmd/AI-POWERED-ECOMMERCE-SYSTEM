from django.contrib import admin

# Register your models here.
from .models import SearchQuery, FAISSIndex

@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display  = ('query','search_type','results_count','user','searched_at')
    list_filter   = ('search_type',)
    search_fields = ('query',)
    readonly_fields = ('searched_at',)

@admin.register(FAISSIndex)
class FAISSIndexAdmin(admin.ModelAdmin):
    list_display  = ('index_type','product_count','is_active','built_at')
    list_filter   = ('index_type','is_active')
    readonly_fields = ('built_at',)
