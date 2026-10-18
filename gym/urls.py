from django.urls import path

from . import views

app_name = 'gym'

urlpatterns = [
    path('', views.home, name='home'),
    path('day/<slug:day>/', views.day, name='day'),
    path('weights/', views.weights, name='weights'),
    path('lift/<slug:slug>/', views.lift, name='lift'),
    path('undo/', views.undo_last, name='undo'),
    path('manifest.webmanifest', views.manifest, name='manifest'),
]
