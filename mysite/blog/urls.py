from django.urls import path
from . import views

urlpatterns = [
    path('api/events/', views.events_list),
    path('api/events/<int:event_id>/join/', views.join_queue),
    path('api/events/<int:event_id>/leave/', views.leave_queue),
    path('api/events/<int:event_id>/position/', views.position),
    path('api/events/<int:event_id>/next/', views.call_next),
]
