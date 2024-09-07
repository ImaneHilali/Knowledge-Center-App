from django.urls import path

from .views import SignUpView, VerificationView

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("verification/", VerificationView.as_view(), name="verification"),

]