from django.db.models import Q
from evaluasi.models import JenisIndeks, BobotIndikatorPeriode

def daftar_indeks_global(request):
    # 1. Proteksi awal: Jika user belum login, jangan berikan data apapun
    if not request.user.is_authenticated:
        return {'indeks_global_list': []}
        
    try:
        user_profile = request.user.profile
        user_role = user_profile.role.upper()
        
        if user_role == 'SUPERADMIN':
            # SUPERADMIN: Buka semua akses ke seluruh master indeks
            indeks_list = JenisIndeks.objects.all().order_by('-tahun_berlaku')
            
        elif user_role == 'OPERATOR':
            # OPERATOR: Sinkronisasi ganda (Berdasarkan OPD DAN Hak Akses Indeks)
            user_opd = user_profile.opd
            
            # Langkah A: Cari ID indeks yang di dalamnya ada indikator untuk OPD ini
            indeks_ids_by_opd = BobotIndikatorPeriode.objects.filter(
                Q(opd_penanggung_jawab__isnull=True) | Q(opd_penanggung_jawab=user_opd)
            ).values_list('jenis_indeks_id', flat=True).distinct()
            
            # Langkah B: Filter dari 'indeks_akses' si user yang juga masuk dalam daftar Langkah A
            indeks_list = user_profile.indeks_akses.filter(
                id__in=indeks_ids_by_opd
            ).order_by('-tahun_berlaku')
            
        elif user_role == 'SUPERVISOR':
            # SUPERVISOR: Sekarang tidak kosong lagi! Kita tampilkan jenis indeks
            # yang ditugaskan kepada supervisor ini untuk bahan menu Verifikasi dinamis
            indeks_list = user_profile.indeks_akses.all().order_by('-tahun_berlaku')
            
        else:
            indeks_list = []
            
        return {'indeks_global_list': indeks_list}
        
    except Exception:
        # Fallback aman jika terjadi anomali (misal superuser Django belum punya profil)
        return {'indeks_global_list': []}