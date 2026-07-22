from django.contrib import admin
from .models import ChatSession, ChatMessage, IntentLabel

class ChatMessageInline(admin.TabularInline):
    model   = ChatMessage
    extra   = 0
    readonly_fields = ('role','content','intent','confidence','created_at')
    can_delete = False

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display  = ('id','user','message_count','handed_off','is_active','created_at')
    list_filter   = ('is_active','handed_off')
    search_fields = ('user__email','session_key')
    inlines       = [ChatMessageInline]
    readonly_fields = ('created_at','updated_at')

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display  = ('session','role','intent','confidence','created_at')
    list_filter   = ('role','intent')
    search_fields = ('content',)
    readonly_fields = ('created_at',)

@admin.register(IntentLabel)
class IntentLabelAdmin(admin.ModelAdmin):
    list_display  = ('intent','text','source')
    list_filter   = ('intent','source')
    search_fields = ('text',)
    actions       = ['retrain_classifier']

    def retrain_classifier(self, request, queryset):
        from ai_chatbot.intent_classifier import train_classifier
        model = train_classifier()
        if model:
            self.message_user(request, 'Intent classifier retrained successfully!')
        else:
            self.message_user(request, 'Not enough data to train.', level='warning')
    retrain_classifier.short_description = 'Retrain intent classifier'
