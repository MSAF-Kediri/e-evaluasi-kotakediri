import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from evaluasi.models import (
    User, ProfileUser, JenisIndeks, KomponenEvaluasi, 
    IndikatorEvaluasi, PilihanJawabanIndikator, TransaksiEvaluasi
)

# Decorator Native untuk Mengunci URL berdasarkan Role
def role_required(allowed_roles=[]):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            # 1. Pastikan user punya profile dan role yang diizinkan
            try:
                if request.user.profile.role in allowed_roles:
                    return view_func(request, *args, **kwargs)
            except Exception:
                pass
            
            # 2. Jika role tidak sesuai, LEMPAR EROR 403 (Akses Dimatikan Total)
            raise PermissionDenied
        return _wrapped_view
    return decorator


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        user_input = request.POST.get('username')  # Ini bisa berisi username asli ATAU nomor NIP
        pass_input = request.POST.get('password')
        
        # 1. LOGIKA UTAMA: Deteksi Login via NIP atau Username
        target_username = user_input # Defaultnya kita anggap dia menginput username asli
        
        try:
            # Coba cari dulu: Apakah user_input ini terdaftar sebagai NIP di ProfileUser?
            profile_by_nip = ProfileUser.objects.get(nip=user_input)
            # Jika ketemu, kita switch target login menggunakan username pasangannya
            target_username = profile_by_nip.user.username
        except ProfileUser.DoesNotExist:
            # Jika tidak ketemu di kolom NIP, biarkan target_username tetap berisi input awal (asumsi username)
            pass

        # 2. Ambil objek User & Profile berdasarkan target_username yang sudah dikunci
        try:
            check_user = User.objects.get(username=target_username)
            profile = check_user.profile
        except (User.DoesNotExist, Exception):
            # Gabungkan pesan eror agar hacker tidak tahu username mana yang valid/salah
            messages.error(request, "Username, NIP, atau Password salah!")
            return render(request, 'evaluasi/login.html')
            
        # 3. Cek Status Pemblokiran Akun
        if not profile.is_active_sw:
            messages.error(request, "Akun Anda TERBLOKIR! Silakan hubungi Superadmin Kominfo untuk mengaktifkannya kembali.")
            return render(request, 'evaluasi/login.html')
            
        # 4. Lakukan Otentikasi Resmi Django menggunakan target_username
        user = authenticate(request, username=target_username, password=pass_input)
        
        if user is not None:
            # Sukses login: reset counter salah login
            profile.salah_login_count = 0
            profile.save()
            
            login(request, user)
            return redirect('dashboard')
        else:
            # Gagal login: Tambah hitungan eror
            profile.salah_login_count += 1
            
            if profile.salah_login_count >= 3:
                profile.is_active_sw = False
                profile.save()
                messages.error(request, "Anda telah salah memasukkan password sebanyak 3 kali. Akun Anda OTOMATIS TERBLOKIR!")
            else:
                sisa_kesempatan = 3 - profile.salah_login_count
                messages.error(request, f"Password salah! Kesempatan mencoba tinggal {sisa_kesempatan} kali lagi.")
                profile.save()
            
    return render(request, 'evaluasi/login.html')

@login_required(login_url='login')
def dashboard_view(request):
    # Ambil data role native dari profile user yang sedang login
    # Kita berikan kondisi aman jika seandainya profile belum terbuat
    try:
        user_role = request.user.profile.role
    except:
        user_role = None
        
    # Inisialisasi status apakah modal password harus otomatis terbuka (jika ada eror saat submit)
    buka_modal_password = False

    # Tangani proses submit ganti password jika ada request POST untuk password
    if request.method == 'POST' and 'submit_password' in request.POST:
        password_lama = request.POST.get('password_lama')
        password_baru = request.POST.get('password_baru')
        konfirmasi_password = request.POST.get('konfirmasi_password')
        
        user = request.user
        buka_modal_password = True # Paksa modal tetap terbuka untuk menampilkan pesan eror
        
        # 1. Validasi password lama
        if not user.check_password(password_lama):
            messages.error(request, "Password lama yang Anda masukkan salah!")
        
        # 2. Validasi kesesuaian password baru
        elif password_baru != konfirmasi_password:
            messages.error(request, "Konfirmasi password baru tidak cocok!")
            
        # 3. Validasi Kompleksitas Password
        elif len(password_baru) < 8:
            messages.error(request, "Password baru harus minimal 8 karakter!")
        elif not re.search(r"[A-Za-z]", password_baru):
            messages.error(request, "Password baru harus mengandung minimal satu huruf!")
        elif not re.search(r"[0-9]", password_baru):
            messages.error(request, "Password baru harus mengandung minimal satu angka!")
        elif not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password_baru):
            messages.error(request, "Password baru harus mengandung minimal satu karakter spesial!")
            
        # 4. Proses simpan jika lolos semua validasi
        else:
            user.set_password(password_baru)
            user.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password Anda berhasil diperbarui!")
            buka_modal_password = False # Tutup modal karena sukses
            return redirect('dashboard')

    context = {
        'user_role': user_role,
        'buka_modal_password': buka_modal_password,
    }
    return render(request, 'evaluasi/dashboard.html', context)

def logout_view(request):
    logout(request)
    messages.info(request, "Anda telah berhasil keluar dari sistem.")
    return redirect('login')

@login_required(login_url='login')
@role_required(allowed_roles=['SUPERADMIN']) # <-- Hanya Superadmin yang bisa ketik URL ini
def master_indikator_view(request):
    return render(request, 'evaluasi/master_indikator.html')