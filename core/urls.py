"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
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
from django.views.generic.base import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('favicon.ico', RedirectView.as_view(url='/static/evaluasi/Logo_Kota_Kediri.png')),

    path('', include('evaluasi.urls')), # Menyambungkan jalur ke urls.py milik app evaluasi
]

# ================= CUSTOM IDENTITY SUPERADMIN PEMDI =================
admin.site.site_header = "Superadmin E-Evaluasi PEMDI"     # Mengubah teks Header besar di atas form login & dashboard admin
admin.site.site_title = "Admin PEMDI Kota Kediri"          # Mengubah teks Title pada Tab Browser (Title Tag)
admin.site.index_title = "Panel Kontrol Master Data"       # Mengubah teks Selamat Datang di halaman utama setelah login admin