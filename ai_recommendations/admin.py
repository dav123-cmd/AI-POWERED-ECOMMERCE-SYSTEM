from django.contrib import admin
from .models import UserProductInteraction, RecommenderModel, SimilarProduct

@admin.register(UserProductInteraction)
class InteractionAdmin(admin.ModelAdmin):
    list_display  = ('user','product','interaction','weight','created_at')
    list_filter   = ('interaction',)
    search_fields = ('user__email','product__name')
    readonly_fields = ('created_at','weight')

@admin.register(RecommenderModel)
class RecommenderModelAdmin(admin.ModelAdmin):
    list_display  = ('version','n_users','n_products','train_loss','is_active','trained_at')
    list_filter   = ('is_active',)
    readonly_fields = ('trained_at',)
    actions       = ['set_active']

    def set_active(self, request, queryset):
        RecommenderModel.objects.all().update(is_active=False)
        queryset.update(is_active=True)
    set_active.short_description = 'Set as active model'

@admin.register(SimilarProduct)
class SimilarProductAdmin(admin.ModelAdmin):
    list_display  = ('product','similar','score')
    search_fields = ('product__name','similar__name')
