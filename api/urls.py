from django.urls import path

from . import views

urlpatterns = [
    path('telebirr/', views.verify_telebirr_payment, name='verify_telebirr_payment'),
    path('telebirr/<str:reference_number>/', views.verify_telebirr_payment_by_reference, name='verify_telebirr_payment_by_reference'),
    path('telebirr/html/', views.fetch_telebirr_receipt_html, name='fetch_telebirr_receipt_html'),
    path('telebirr/html/<str:reference_number>/', views.fetch_telebirr_receipt_html_by_reference, name='fetch_telebirr_receipt_html_by_reference'),
]
