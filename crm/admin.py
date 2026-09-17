from django.contrib import admin

from .models import (
    Contact, ContactStatusLog, Deal, EmailCampaign, EmailSend, Meeting, Note, SavedRecipient, TodoBlock, Unsubscribe,
)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'phone', 'status', 'pipeline', 'region', 'owner', 'created_at')
    list_filter = ('status', 'lost_reason', 'pipeline', 'region', 'owner')
    search_fields = ('name', 'company', 'phone', 'email')
    list_select_related = ('owner',)
    actions = ['assign_to_me']

    @admin.action(description='Assign selected leads to me')
    def assign_to_me(self, request, queryset):
        updated = queryset.update(owner=request.user)
        self.message_user(request, f'Assigned {updated} lead(s) to {request.user.get_username()}.')


@admin.register(ContactStatusLog)
class ContactStatusLogAdmin(admin.ModelAdmin):
    list_display = ('contact', 'from_status', 'to_status', 'changed_by', 'changed_at')
    list_filter = ('to_status', 'changed_by')
    list_select_related = ('contact', 'changed_by')


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'contact', 'meeting_type', 'scheduled_at', 'completed')
    list_filter = ('completed', 'meeting_type')
    list_select_related = ('contact',)


class EmailSendInline(admin.TabularInline):
    model = EmailSend
    extra = 0
    readonly_fields = ('email', 'contact', 'status', 'error', 'sent_at')


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ('subject', 'from_email', 'status', 'created_by', 'created_at')
    inlines = [EmailSendInline]


admin.site.register(Deal)
admin.site.register(Note)
admin.site.register(TodoBlock)
admin.site.register(SavedRecipient)
admin.site.register(Unsubscribe)
