from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from .forms import UserLoginForm, NewUserForm


# Create your views here.


def index(request):
    return render(request, 'home.html')


def login_view(request):
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('index')
        login_error = True
    else:
        form = UserLoginForm()
        login_error = False
    return render(request, "login.html", {"form": form, "login_error": login_error})


def logout_view(request):
    logout(request)
    return redirect('login_view')


def register_view(request):
    if request.method == "POST":
        form = NewUserForm(request.POST)
        print(form.errors)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("index")
    form = NewUserForm()
    return render(request=request, template_name="register.html", context={"form": form})
