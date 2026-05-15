from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('contacts/', views.contact_list, name='contact_list'),
    path('contacts/us/', views.us_leads, name='us_leads'),
    path('contacts/sa/', views.sa_leads, name='sa_leads'),
    path('contacts/inactive/', views.inactive_leads, name='inactive_leads'),
    path('contacts/new/', views.contact_create, name='contact_create'),
    path('contacts/<int:pk>/', views.contact_detail, name='contact_detail'),
    path('contacts/<int:pk>/edit/', views.contact_edit, name='contact_edit'),
    path('contacts/<int:pk>/delete/', views.contact_delete, name='contact_delete'),
    path('deals/', views.deal_list, name='deal_list'),
    path('deals/new/', views.deal_create, name='deal_create'),
    path('deals/<int:pk>/', views.deal_detail, name='deal_detail'),
    path('deals/<int:pk>/edit/', views.deal_edit, name='deal_edit'),
    path('deals/<int:pk>/delete/', views.deal_delete, name='deal_delete'),
    path('notes/<int:pk>/delete/', views.note_delete, name='note_delete'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('meetings/new/', views.meeting_create, name='meeting_create'),
    path('meetings/<int:pk>/edit/', views.meeting_edit, name='meeting_edit'),
    path('meetings/<int:pk>/delete/', views.meeting_delete, name='meeting_delete'),
    path('leads/generator/', views.leads_generator, name='leads_generator'),
]
