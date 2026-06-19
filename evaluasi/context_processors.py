from django.db.models import Q
from evaluasi.models import JenisIndeks, BobotIndikatorPeriode, TransaksiEvaluasi, Notifikasi


def _hitung_indeks_sah_total(indeks_list, user_opd):
    """
    Versi OPTIMIZED — hanya 2 query DATABASE TOTAL, tidak peduli berapa
    banyak indeks yang dicek (bukan per-indeks seperti versi awal).

    Mengembalikan SET berisi id JenisIndeks yang sudah "sah total"
    (seluruh indikator tanggung jawab OPD ini sudah VERIFIED semua).
    """
    indeks_ids = [i.id for i in indeks_list]
    if not indeks_ids:
        return set()

    # QUERY 1: Ambil semua pasangan (jenis_indeks_id, indikator_id) yang relevan untuk OPD ini
    bobot_rows = (
        BobotIndikatorPeriode.objects
        .filter(jenis_indeks_id__in=indeks_ids)
        .filter(Q(opd_penanggung_jawab__isnull=True) | Q(opd_penanggung_jawab=user_opd))
        .values_list("jenis_indeks_id", "indikator_id")
    )

    indikator_per_indeks = {}  # {jenis_indeks_id: set(indikator_id, ...)}
    for jenis_indeks_id, indikator_id in bobot_rows:
        indikator_per_indeks.setdefault(jenis_indeks_id, set()).add(indikator_id)

    semua_indikator_ids = {iid for ids in indikator_per_indeks.values() for iid in ids}
    if not semua_indikator_ids:
        return set()  # Tidak ada indikator sama sekali -> tidak ada yang dianggap "sah"

    # QUERY 2: Ambil pasangan (jenis_indeks_id, indikator_id) yang statusnya VERIFIED
    verified_rows = (
        TransaksiEvaluasi.objects
        .filter(
            indeks_aktif_id__in=indeks_ids,
            indikator_id__in=semua_indikator_ids,
            status="VERIFIED",
        )
        .values_list("indeks_aktif_id", "indikator_id")
    )

    verified_per_indeks = {}  # {jenis_indeks_id: set(indikator_id, ...)}
    for jenis_indeks_id, indikator_id in verified_rows:
        verified_per_indeks.setdefault(jenis_indeks_id, set()).add(indikator_id)

    # Bandingkan: indeks dianggap "sah total" jika set indikator VERIFIED-nya
    # SAMA DENGAN set seluruh indikator yang jadi tanggung jawab OPD ini
    indeks_sah_ids = set()
    for jenis_indeks_id, indikator_ids in indikator_per_indeks.items():
        verified_ids = verified_per_indeks.get(jenis_indeks_id, set())
        if indikator_ids and indikator_ids.issubset(verified_ids):
            indeks_sah_ids.add(jenis_indeks_id)

    return indeks_sah_ids


def daftar_indeks_global(request):
    # 1. Proteksi awal: Jika user belum login, jangan berikan data apapun
    if not request.user.is_authenticated:
        return {
            'indeks_global_list': [],
            'indeks_belum_sah_list': [],
            'notif_unread_count': 0,
        }

    try:
        user_profile = request.user.profile
        user_role = user_profile.role.upper()

        indeks_belum_sah_list = None  # Default: akan disamakan dgn indeks_list di akhir

        if user_role == 'SUPERADMIN':
            # SUPERADMIN: Buka semua akses ke seluruh master indeks (termasuk yang sudah sah)
            indeks_list = JenisIndeks.objects.all().order_by('-tahun_berlaku')

        elif user_role == 'OPERATOR':
            # OPERATOR: Sinkronisasi ganda (Berdasarkan OPD DAN Hak Akses Indeks)
            user_opd = user_profile.opd

            # Langkah A: Cari ID indeks yang di dalamnya ada indikator untuk OPD ini
            indeks_ids_by_opd = BobotIndikatorPeriode.objects.filter(
                Q(opd_penanggung_jawab__isnull=True) | Q(opd_penanggung_jawab=user_opd)
            ).values_list('jenis_indeks_id', flat=True).distinct()

            # Langkah B: Filter dari 'indeks_akses' si user yang juga masuk dalam daftar Langkah A
            # -> Dipakai untuk "Hasil Indeks" (tetap menampilkan SEMUA, termasuk yang sudah sah)
            indeks_list = list(
                user_profile.indeks_akses.filter(
                    id__in=indeks_ids_by_opd
                ).order_by('-tahun_berlaku')
            )

            # Langkah C: Hitung sekaligus (2 query total) mana saja yang sudah SAH TOTAL
            indeks_sah_ids = _hitung_indeks_sah_total(indeks_list, user_opd)

            # Versi khusus untuk "Isi Kuesioner" -> exclude yang sudah sah total
            indeks_belum_sah_list = [
                indeks for indeks in indeks_list
                if indeks.id not in indeks_sah_ids
            ]

        elif user_role == 'SUPERVISOR':
            # SUPERVISOR: Tampilkan jenis indeks yang ditugaskan untuk menu Verifikasi dinamis
            indeks_list = user_profile.indeks_akses.all().order_by('-tahun_berlaku')

        else:
            indeks_list = []

        # Untuk role selain OPERATOR, "belum sah" = sama saja dengan daftar penuh
        if indeks_belum_sah_list is None:
            indeks_belum_sah_list = indeks_list

        # ------------------------------------------------------------------
        # Hitung notifikasi belum dibaca (hanya relevan untuk OPERATOR)
        # ------------------------------------------------------------------
        notif_unread_count = 0
        if user_role == 'OPERATOR':
            notif_unread_count = Notifikasi.objects.filter(
                penerima=request.user,
                sudah_dibaca=False,
            ).count()

        return {
            'indeks_global_list': indeks_list,             # dipakai: Hasil Indeks (semua, termasuk sah)
            'indeks_belum_sah_list': indeks_belum_sah_list, # dipakai: Isi Kuesioner / Aksi Cepat (exclude sah)
            'notif_unread_count': notif_unread_count,
        }

    except Exception:
        # Fallback aman jika terjadi anomali (misal superuser Django belum punya profil)
        return {
            'indeks_global_list': [],
            'indeks_belum_sah_list': [],
            'notif_unread_count': 0,
        }