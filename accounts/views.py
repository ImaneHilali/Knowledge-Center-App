from django.contrib.auth import login
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views import View

# Create your views here.
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, FormView
from django.contrib import messages
import requests
from accounts.forms import VerificationForm, CustomUserCreationForm
import random
from django.contrib.auth.models import User


def send_verification_code_to_supervisor(code):
    api_key = 'f4cadfefe3bf2d0c2b87cab84d184670-f52e92ba-aabb-4fa7-9d82-a22ab9436fb4'
    base_url = 'https://5y3p3x.api.infobip.com'
    endpoint = '/sms/2/text/advanced'
    url = f"{base_url}{endpoint}"
    headers = {
        'Authorization': f'App {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    payload = {
        "messages": [
            {
                "from": "InfoSMS",
                "destinations": [
                    {
                        "to": "+212620811061"
                    }
                ],
                "text": f"Your verification code is: {code}"
            }
        ]
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        print("Message sent successfully")
    else:
        print(f"Failed to send message: {response.status_code} - {response.text}")


@method_decorator(csrf_exempt, name='dispatch')
class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy("verification")
    template_name = "registration/signup.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        verification_code = random.randint(1000, 9999)
        send_verification_code_to_supervisor(verification_code)
        self.request.session['verification_code'] = verification_code
        self.request.session['user_id'] = self.object.id
        return JsonResponse({'success': True, 'redirect_url': self.success_url})

    def form_invalid(self, form):
        errors = {field: error.get_json_data() for field, error in form.errors.items()}
        return JsonResponse({'success': False, 'errors': errors}, status=400)

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


class VerificationView(View):
    template_name = "registration/verification.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        input_code = request.POST.get('verification_code')
        session_code = request.session.get('verification_code')

        if str(input_code) == str(session_code):
            user_id = request.session.get('user_id')
            user = User.objects.get(id=user_id)
            user.is_active = True
            user.save()

            login(request, user)

            del request.session['verification_code']
            del request.session['user_id']
            return redirect('home')
        else:
            messages.error(request, "The verification code is incorrect. Please try again.")
            return render(request, self.template_name)