"""
URL configuration for cbstg project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from .views import index, login_view, logout_view, register_view

urlpatterns = [
    path("", index, name='index'),
    path("login/", login_view, name='login_view'),
    path("logout/", logout_view, name='logout_view'),
    path("register/", register_view, name='register_view'),
    path("", include('cbstg_app.urls')),
    path('admin/', admin.site.urls),

]
