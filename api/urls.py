from django.urls import path

from . import views

urlpatterns = [
    path('telebirr/', views.verify_telebirr_payment, name='verify_telebirr_payment'),
    path('telebirr/<str:reference_number>/', views.verify_telebirr_payment_by_reference, name='verify_telebirr_payment_by_reference'),
]
