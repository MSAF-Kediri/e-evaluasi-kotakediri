from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    
    # JALUR BARU 1: Kuesioner Dinamis (Menerima parameter string seperti 'PEMDI')
    path('kuesioner/<str:kode_indeks>/', views.kuesioner_isi_view, name='kuesioner_isi'),
    
    # JALUR BARU 2: Daftar Verifikasi untuk Supervisor & Superadmin
    path('verifikasi/', views.verifikasi_list_view, name='verifikasi_list'),
    
    # JALUR BARU 3: Halaman Master Indikator Eksklusif Superadmin
    path('master-indikator/', views.master_indikator_view, name='master_indikator'),

    # JALUR BARU 4: Ping ringan untuk memperbarui sesi tanpa reload halaman
    path('ping-sesi/', views.ping_sesi_view, name='ping_sesi'),

    # JALUR BARU 5: AJAX Polling — cek perubahan data kuesioner secara ringan
    path('kuesioner/<str:kode_indeks>/poll/', views.poll_kuesioner_view, name='poll_kuesioner'),

    # JALUR BARU 6: Halaman Hasil Nilai Indeks per OPD
    path('hasil/<str:kode_indeks>/', views.hasil_indeks_view, name='hasil_indeks'),

    # JALUR BARU 7: Log Aktivitas Pengguna
    path('activity-log/', views.activity_log_view, name='activity_log'),

    # JALUR BARU 8: AJAX — ambil daftar notifikasi (dropdown bell icon)
    path('notifikasi/fetch/', views.notifikasi_fetch_view, name='notifikasi_fetch'),

    # JALUR BARU 9: AJAX — tandai satu / semua notifikasi sudah dibaca
    path('notifikasi/baca/', views.notifikasi_baca_view, name='notifikasi_baca'),

    # JALUR BARU 10: Polling ringan — cek jumlah notif belum dibaca (untuk badge bell)
    path('notifikasi/poll/', views.notifikasi_poll_view, name='notifikasi_poll'),
]