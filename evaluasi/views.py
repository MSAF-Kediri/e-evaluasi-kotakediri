import re
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from evaluasi.models import (
    OPD,
    User,
    ProfileUser,
    JenisIndeks,
    KomponenEvaluasi,
    IndikatorEvaluasi,
    PilihanJawabanIndikator,
    TransaksiEvaluasi,
    BobotIndikatorPeriode,
    ActivityLog,
    Notifikasi,
)
from django.db.models import Q, Prefetch, Max
from django.http import JsonResponse
from decimal import Decimal
from collections import defaultdict


@login_required(login_url="login")
def ping_sesi_view(request):
    """
    Endpoint ringan untuk menyegarkan sesi Django tanpa reload halaman.
    Dipanggil via fetch() dari JavaScript setiap kali ada aktivitas pengguna.
    Cukup mengakses view ini sudah otomatis memperpanjang sesi Django.
    """
    return JsonResponse({"status": "ok"})

# ==============================================================================
# 1. DECORATOR NATIVE DENGAN HAK AKSES SAKTI SUPERADMIN (RETAINED)
# ==============================================================================
def role_required(allowed_roles=[]):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            try:
                user_role = request.user.profile.role
            except Exception:
                raise PermissionDenied

            is_allowed = False
            if user_role.upper() == "SUPERADMIN":
                is_allowed = True
            elif user_role.upper() in [role.upper() for role in allowed_roles]:
                is_allowed = True

            if is_allowed:
                return view_func(request, *args, **kwargs)

            raise PermissionDenied
        return _wrapped_view
    return decorator

# ==============================================================================
# HELPER: CATAT AKTIVITAS USER KE DATABASE (ACTIVITY LOG)
# ==============================================================================
def catat_aktivitas(request, aksi, deskripsi="", indeks=None, opd=None):
    """
    Fungsi helper untuk mencatat setiap aktivitas penting ke tabel ActivityLog.
    Otomatis membaca IP address dari request header.
    """
    try:
        user = request.user if request.user.is_authenticated else None
        user_opd = opd
        if not user_opd and user and hasattr(user, 'profile') and user.profile.opd:
            user_opd = user.profile.opd

        # Ambil IP asli bahkan di belakang proxy/nginx
        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        )

        ActivityLog.objects.create(
            user=user,
            opd=user_opd,
            aksi=aksi,
            deskripsi=deskripsi,
            indeks=indeks,
            ip_address=ip or None,
        )
    except Exception:
        pass  # Jangan biarkan error logging menghentikan proses utama

# ==============================================================================
# HELPER: KIRIM NOTIFIKASI KE OPERATOR SETELAH PROSES VERIFIKASI SUPERVISOR
# ==============================================================================
def kirim_notifikasi_ke_operator(transaksi, tipe_aksi):
    """
    Buat record Notifikasi untuk semua operator dari OPD pengisi transaksi ini.
    tipe_aksi: 'APPROVE' atau 'REJECT'
    Dipanggil setelah transaksi.save() di verifikasi_list_view.
    """
    try:
        opd = transaksi.opd_pengisi_terakhir
        if not opd:
            return
 
        # Cari semua user OPERATOR dari OPD yang sama
        operator_list = User.objects.filter(
            profile__role="OPERATOR",
            profile__opd=opd,
            profile__is_active_sw=True,
        )
 
        if tipe_aksi == "APPROVE":
            judul = f"✅ Indikator {transaksi.indikator.nomor_indikator} Disetujui"
            pesan = (
                f"Indikator {transaksi.indikator.nomor_indikator} "
                f"({transaksi.indikator.nama_indikator}) pada instrumen "
                f"{transaksi.indeks_aktif.kode_indeks} telah diverifikasi dan dinyatakan SAH."
            )
            if transaksi.catatan_supervisor:
                pesan += f"\n\nRekomendasi Supervisor: {transaksi.catatan_supervisor}"
        else:  # REJECT
            judul = f"❌ Indikator {transaksi.indikator.nomor_indikator} Dikembalikan"
            pesan = (
                f"Indikator {transaksi.indikator.nomor_indikator} "
                f"({transaksi.indikator.nama_indikator}) pada instrumen "
                f"{transaksi.indeks_aktif.kode_indeks} dikembalikan ke draf untuk direvisi."
            )
            if transaksi.catatan_supervisor:
                pesan += f"\n\nAlasan Supervisor: {transaksi.catatan_supervisor}"
 
        # Buat notifikasi untuk setiap operator — bulk_create untuk efisiensi
        notif_list = [
            Notifikasi(
                penerima=operator,
                tipe=tipe_aksi,
                judul=judul,
                pesan=pesan,
                transaksi=transaksi,
                indeks=transaksi.indeks_aktif,
            )
            for operator in operator_list
        ]
        if notif_list:
            Notifikasi.objects.bulk_create(notif_list)
 
    except Exception:
        pass  # Jangan biarkan error notifikasi menghentikan proses utama

# ==============================================================================
# 2. PROSES LOGOUT, LOGIN, & DASHBOARD (RETAINED & AUDITED)
# ==============================================================================
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        user_input = request.POST.get("username")
        pass_input = request.POST.get("password")
        target_username = user_input

        try:
            profile_by_nip = ProfileUser.objects.get(nip=user_input)
            target_username = profile_by_nip.user.username
        except ProfileUser.DoesNotExist:
            pass

        try:
            check_user = User.objects.get(username=target_username)
            profile = check_user.profile
        except (User.DoesNotExist, Exception):
            messages.error(request, "Username, NIP, atau Password salah!")
            return render(request, "evaluasi/login.html")

        if not profile.is_active_sw:
            messages.error(
                request,
                "Akun Anda TERBLOKIR! Silakan hubungi Superadmin Kominfo untuk mengaktifkannya kembali.",
            )
            return render(request, "evaluasi/login.html")

        user = authenticate(request, username=target_username, password=pass_input)

        if user is not None:
            profile.salah_login_count = 0
            profile.save()
            login(request, user)
            # === CATAT AKTIVITAS LOGIN ===
            catat_aktivitas(
                request, "LOGIN",
                deskripsi=f"Login berhasil dari IP {request.META.get('REMOTE_ADDR', '-')}"
            )
            return redirect("dashboard")
        else:
            profile.salah_login_count += 1
            if profile.salah_login_count >= 3:
                profile.is_active_sw = False
                profile.save()
                messages.error(
                    request,
                    "Anda telah salah memasukkan password sebanyak 3 kali. Akun Anda OTOMATIS TERBLOKIR!",
                )
            else:
                sisa_kesempatan = 3 - profile.salah_login_count
                messages.error(
                    request,
                    f"Password salah! Kesempatan mencoba tinggal {sisa_kesempatan} kali lagi.",
                )
                profile.save()

    return render(request, "evaluasi/login.html")


@login_required(login_url="login")
def dashboard_view(request):
    try:
        user_profile = request.user.profile
        user_role    = user_profile.role.upper()
    except Exception:
        user_profile = None
        user_role    = None
 
    buka_modal_password = False
 
    # ------------------------------------------------------------------
    # PROSES GANTI PASSWORD (tidak berubah dari versi lama)
    # ------------------------------------------------------------------
    if request.method == "POST" and "submit_password" in request.POST:
        password_lama       = request.POST.get("password_lama")
        password_baru       = request.POST.get("password_baru")
        konfirmasi_password = request.POST.get("konfirmasi_password")
 
        user = request.user
        buka_modal_password = True
 
        if not user.check_password(password_lama):
            messages.error(request, "Password lama yang Anda masukkan salah!")
        elif password_baru != konfirmasi_password:
            messages.error(request, "Konfirmasi password baru tidak cocok!")
        elif len(password_baru) < 8:
            messages.error(request, "Password baru harus minimal 8 karakter!")
        elif not re.search(r"[A-Za-z]", password_baru):
            messages.error(request, "Password baru harus mengandung minimal satu huruf!")
        elif not re.search(r"[0-9]", password_baru):
            messages.error(request, "Password baru harus mengandung minimal satu angka!")
        elif not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password_baru):
            messages.error(request, "Password baru harus mengandung minimal satu karakter spesial!")
        else:
            user.set_password(password_baru)
            user.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password Anda berhasil diperbarui!")
            buka_modal_password = False
            catat_aktivitas(request, "GANTI_PASSWORD", deskripsi="Password berhasil diubah")
            return redirect("dashboard")
 
    # ------------------------------------------------------------------
    # STATISTIK RINGKASAN — disesuaikan per role
    # ------------------------------------------------------------------
    stats = {}
 
    if user_role == "OPERATOR" and user_profile and user_profile.opd:
        # Stats berdasarkan indeks yang bisa diakses operator ini
        indeks_aktif = user_profile.indeks_akses.all()

        total  = TransaksiEvaluasi.objects.filter(indeks_aktif__in=indeks_aktif).count()
        draf   = TransaksiEvaluasi.objects.filter(indeks_aktif__in=indeks_aktif, status="DRAF").count()
        submit = TransaksiEvaluasi.objects.filter(indeks_aktif__in=indeks_aktif, status="SUBMITTED").count()
        verify = TransaksiEvaluasi.objects.filter(indeks_aktif__in=indeks_aktif, status="VERIFIED").count()
 
        stats = {
            "total":        total,
            "draf":         draf,
            "submitted":    submit,
            "verified":     verify,
            "indeks_aktif": indeks_aktif,
        }
 
    elif user_role == "SUPERVISOR":
        indeks_akses = user_profile.indeks_akses.all()
 
        menunggu  = TransaksiEvaluasi.objects.filter(
            status="SUBMITTED", indeks_aktif__in=indeks_akses
        ).count()
        diverif   = TransaksiEvaluasi.objects.filter(
            status="VERIFIED", indeks_aktif__in=indeks_akses
        ).count()
        # Hitung indeks yang sedang aktif diisi (ada transaksi)
        # total_indeks_aktif = TransaksiEvaluasi.objects.filter(
        #     indeks_aktif__in=indeks_akses
        # ).values("indeks_aktif").distinct().count()
 
        stats = {
            "menunggu": menunggu,
            "diverifikasi": diverif,
            "total_indeks_aktif": indeks_akses.count(),  # Total indeks yang bisa diaudit supervisor ini
        }
 
    elif user_role == "SUPERADMIN":
        total_submit = TransaksiEvaluasi.objects.filter(status="SUBMITTED").count()
        total_verify = TransaksiEvaluasi.objects.filter(status="VERIFIED").count()
        total_user   = ProfileUser.objects.filter(is_active_sw=True).count()
        total_indeks = JenisIndeks.objects.count()
 
        stats = {
            "total_indeks_aktif":    total_indeks,   # reuse slot — tampilkan jumlah indeks aktif
            "menunggu":     total_submit,
            "diverifikasi": total_verify,
            "total_user":   total_user,
        }
 
    context = {
        "user_role":           user_role,
        "buka_modal_password": buka_modal_password,
        "stats":               stats,
    }
    return render(request, "evaluasi/dashboard.html", context)


def logout_view(request):
    if request.user.is_authenticated:
        catat_aktivitas(request, "LOGOUT", deskripsi="User logout dari sistem")
    logout(request)
    messages.info(request, "Anda telah berhasil keluar dari sistem.")
    return redirect("login")


# ==============================================================================
# 3. VIEWS UTAMA: KUESIONER DINAMIS (SINKRON BERBASIS INSTITUSI / OPD)
# ==============================================================================
@login_required(login_url="login")
@role_required(allowed_roles=["OPERATOR", "SUPERADMIN"])
def kuesioner_isi_view(request, kode_indeks="PEMDI"):
    indeks_aktif = get_object_or_404(JenisIndeks, kode_indeks=kode_indeks)
    user_profile = request.user.profile
    user_role = user_profile.role.upper()
    user_opd = user_profile.opd # Singkat akses OPD pengisi

    # --------------------------------------------------------------------------
    # VALIDASI GUARDRAIL: CEK APAKAH USER BOLEH MENGAKSES INDEKS INI
    # --------------------------------------------------------------------------
    if user_role != "SUPERADMIN" and not user_profile.indeks_akses.filter(id=indeks_aktif.id).exists():
        messages.error(
            request, 
            f"⛔ AKSES DITOLAK! Akun Anda tidak terdaftar untuk mengisi instrumen {indeks_aktif.kode_indeks}."
        )
        return redirect("dashboard")
    # --------------------------------------------------------------------------

    # --------------------------------------------------------------------------
    # A. STRATEGI PENYARINGAN INDIKATOR BERDASARKAN ROLE LOGIN
    # --------------------------------------------------------------------------
    if user_role == "SUPERADMIN":
        bobot_assigned = BobotIndikatorPeriode.objects.filter(
            jenis_indeks=indeks_aktif
        ).values_list("indikator_id", flat=True)
    else:
        bobot_assigned = (
            BobotIndikatorPeriode.objects.filter(jenis_indeks=indeks_aktif)
            .filter(
                Q(opd_penanggung_jawab__isnull=True) | Q(opd_penanggung_jawab=user_opd)
            )
            .values_list("indikator_id", flat=True)
        )

    indikator_ids = list(bobot_assigned)
    
    # Buat cetakan queryset indikator yang sudah dikunci sesuai hak akses indeks/OPD
    indikator_terfilter = IndikatorEvaluasi.objects.filter(
        id__in=indikator_ids
    ).prefetch_related("pilihan_jawaban")

    # ==============================================================================
    # BANGUN TREE KOMPOSISI KOMPONEN + INDIKATOR SECARA REKURSIF
    # ==============================================================================
    # Ambil SEMUA komponen yang relevan sekaligus (1 query)
    semua_komponen = KomponenEvaluasi.objects.filter(
        indikator_list__id__in=indikator_ids
    ).distinct().prefetch_related(
        Prefetch("indikator_list", queryset=indikator_terfilter)
    )

    # Kumpulkan semua ancestor ID agar tree tidak putus di tengah
    ancestor_ids = set()
    for komp in semua_komponen:
        current = komp.parent
        while current:
            ancestor_ids.add(current.id)
            current = current.parent

    # Gabungkan: komponen berindikator + semua ancestornya
    semua_ids = set(k.id for k in semua_komponen) | ancestor_ids
    semua_node = KomponenEvaluasi.objects.filter(
        id__in=semua_ids
    ).prefetch_related(
        Prefetch("indikator_list", queryset=indikator_terfilter),
        "indikator_list__pilihan_jawaban",  # ← tambah ini
    )

    # Bangun tree di Python — O(n), tidak ada query tambahan
    node_map = {n.id: n for n in semua_node}
    for node in semua_node:
        node.children = []  # inject attribute dinamis

    for node in semua_node:
        if node.parent_id and node.parent_id in node_map:
            node_map[node.parent_id].children.append(node)

    # Root = node tanpa parent
    komponen_list = sorted(
        [n for n in semua_node if n.parent_id is None],
        key=lambda x: x.kode_komponen
    )

    # Sort children di tiap node
    def sortchildren(node):
        node.children.sort(key=lambda x: x.kode_komponen)
        for child in node.children:
            sortchildren(child)

    for root in komponen_list:
        sortchildren(root)
    # END BANGUN TREE KOMPOSISI KOMPONEN + INDIKATOR SECARA REKURSIF

    # --------------------------------------------------------------------------
    # B. PROSES MANIPULASI DATA JAWABAN (POST METHOD)
    # --------------------------------------------------------------------------
    if request.method == "POST":
        action = request.POST.get("action")

        # ----------------------------------------------------------------------
        # AKSI A: SUBMIT KOLEKTIF SATU HALAMAN (BENTENG BAJA ANTI-BYPASS SERVER)
        # ----------------------------------------------------------------------
        if action == "submit_kuesioner_halaman":
            total_indikator_count = len(indikator_ids)
            
            # Validasi: hitung transaksi kolektif yang sudah terisi untuk indeks ini
            real_terisi_count = TransaksiEvaluasi.objects.filter(
                indeks_aktif=indeks_aktif,
                indikator_id__in=indikator_ids,
                pilihan_mandiri__isnull=False
            ).count()
            
            if real_terisi_count < total_indikator_count:
                messages.error(
                    request, 
                    f"🚨 Belum semua indikator diisi! "
                    f"Baru {real_terisi_count} dari {total_indikator_count} indikator yang terisi. "
                    f"Silakan lengkapi terlebih dahulu!"
                )
                return redirect("kuesioner_isi", kode_indeks=kode_indeks)
            
            # Submit: ubah status semua transaksi indeks ini ke SUBMITTED
            TransaksiEvaluasi.objects.filter(
                indeks_aktif=indeks_aktif, 
                indikator_id__in=indikator_ids,
                status="DRAF"
            ).update(status="SUBMITTED")

            catat_aktivitas(
                request, "SUBMIT",
                deskripsi=f"Submit kuesioner {kode_indeks} — {real_terisi_count} indikator",
                indeks=indeks_aktif,
            )

            messages.success(
                request,
                "🚀 Sukses! Seluruh instrumen kuesioner berhasil dikirim ke Supervisor.",
            )
            return redirect("kuesioner_isi", kode_indeks=kode_indeks)

        # Parameter default kiriman dari dalam modal individual
        indikator_id = request.POST.get("indikator_id")
        pilihan_id = request.POST.get("pilihan_id")
        link_bukti = request.POST.get("link_bukti_dukung", "").strip()
        catatan = request.POST.get("catatan_opd", "").strip()

        indikator = get_object_or_404(IndikatorEvaluasi, id=indikator_id)

        # ----------------------------------------------------------------------
        # AKSI B: RESET / HAPUS JAWABAN INDIKATOR INDIVIDUAL (BERBASIS OPD)
        # ----------------------------------------------------------------------
        if action == "clear_jawaban":
            TransaksiEvaluasi.objects.filter(
                indeks_aktif=indeks_aktif, indikator=indikator
            ).delete()

            catat_aktivitas(
                request, "HAPUS_JAWABAN",
                deskripsi=f"Hapus jawaban Indikator {indikator.nomor_indikator} — {kode_indeks}",
                indeks=indeks_aktif,
            )

            messages.success(
                request,
                f"🗑️ Jawaban Indikator {indikator.nomor_indikator} berhasil dikosongkan.",
            )
            return redirect("kuesioner_isi", kode_indeks=kode_indeks)

        # ----------------------------------------------------------------------
        # AKSI C: SIMPAN / UPDATE DATA DRAF INDIKATOR INDIVIDUAL (KOLABORATIF)
        # ----------------------------------------------------------------------
        pilihan = None
        if indikator.tipe_penilaian == "INPUT_ANGKA":
            # Untuk tipe input angka manual, buat/ambil PilihanJawaban dinamis
            nilai_input = request.POST.get("nilai_angka_input", "").strip()
            if nilai_input:
                try:
                    nilai_decimal = Decimal(nilai_input)
                    pilihan, _ = PilihanJawabanIndikator.objects.get_or_create(
                        indikator=indikator,
                        nilai_angka=nilai_decimal,
                        defaults={
                            "label_level": f"Nilai {nilai_decimal}",
                            "narasi_kriteria": f"Input angka manual: {nilai_decimal}",
                        },
                    )
                except Exception:
                    messages.error(request, f"⛔ Nilai angka tidak valid untuk Indikator {indikator.nomor_indikator}.")
                    return redirect("kuesioner_isi", kode_indeks=kode_indeks)
        elif pilihan_id:
            pilihan = get_object_or_404(PilihanJawabanIndikator, id=pilihan_id)

        # Proteksi: cek apakah transaksi kolektif sudah terkunci (SUBMITTED/VERIFIED)
        transaksi_lama = TransaksiEvaluasi.objects.filter(
            indeks_aktif=indeks_aktif, indikator=indikator
        ).first()

        if transaksi_lama and transaksi_lama.status in ["SUBMITTED", "VERIFIED"]:
            messages.error(
                request,
                f"⛔ Gagal! Indikator {indikator.nomor_indikator} sudah dikunci karena sedang dalam proses audit.",
            )
            return redirect("kuesioner_isi", kode_indeks=kode_indeks)

        # Simpan jawaban kolektif — kunci pencarian hanya indeks + indikator
        transaksi, created = TransaksiEvaluasi.objects.update_or_create(
            indeks_aktif=indeks_aktif,
            indikator=indikator,
            defaults={
                "pilihan_mandiri": pilihan,
                "link_bukti_dukung": link_bukti if link_bukti else None,
                "catatan_opd": catatan if catatan else None,
                "status": "DRAF",
                "opd_pengisi_terakhir": user_opd,   # audit trail: siapa OPD terakhir edit
                "user_updated_by": request.user,     # audit trail: siapa user terakhir edit
            },
        )

        if created:
            messages.success(
                request,
                f"💾 Jawaban Indikator {indikator.nomor_indikator} berhasil disimpan ke draf OPD.",
            )
        else:
            messages.success(
                request,
                f"🔄 Isian Indikator {indikator.nomor_indikator} berhasil diperbarui secara kolektif.",
            )

        catat_aktivitas(
            request, "SIMPAN_JAWABAN",
            deskripsi=f"{'Simpan baru' if created else 'Update'} Indikator {indikator.nomor_indikator} — {kode_indeks}",
            indeks=indeks_aktif,
        )

        return redirect("kuesioner_isi", kode_indeks=kode_indeks)

    # --------------------------------------------------------------------------
    # C. ALUR PENYAJIAN DATA KUESIONER (GET METHOD)
    # --------------------------------------------------------------------------
    # Kolaboratif: semua role lihat transaksi yang sama (satu set per indeks)
    transaksi_query = TransaksiEvaluasi.objects.filter(indeks_aktif=indeks_aktif)

    transaksi_user = transaksi_query.select_related(
        "pilihan_mandiri", "opd_pengisi_terakhir"
    )

    # Petakan ke Python dictionary untuk kelancaran looping rendering template
    jawaban_map = {t.indikator_id: t for t in transaksi_user}

    # Evaluasi status lembar kerja kontrol halaman
    list_status = [t.status for t in transaksi_user]
    total_indikator_count = len(indikator_ids)

    if not list_status:
        status_halaman = "KOSONG"
    elif "DRAF" in list_status:
        status_halaman = "DRAF"
    elif "SUBMITTED" in list_status:
        status_halaman = "SUBMITTED"
    elif len(list_status) == total_indikator_count and all(s == "VERIFIED" for s in list_status):
        # VERIFIED valid hanya jika SELURUH indikator sudah punya transaksi DAN semuanya VERIFIED
        status_halaman = "VERIFIED"
    else:
        # Ada indikator yang belum diisi sama sekali, sisanya VERIFIED -> treat sebagai DRAF
        # supaya tombol kirim ke supervisor tetap tampil (terkunci karena belum lengkap)
        status_halaman = "DRAF"
    
    # Flatten semua indikator dari tree ke list datar
    def flatten_indikator(node_list):
        result = []
        def _walk(nodes):
            for node in nodes:
                for ind in node.indikator_list.all():
                    result.append((node, ind))
                _walk(node.children)
        _walk(node_list)
        return result

    semua_indikator_flat = flatten_indikator(komponen_list)

    context = {
        "indeks_aktif": indeks_aktif,
        "komponen_list": komponen_list,
        "jawaban_map": jawaban_map,
        "status_halaman": status_halaman,
        "total_indikator_count": total_indikator_count,
        "semua_indikator_flat": semua_indikator_flat,  # ← tambah ini
    }
    
    # === TARUH DI SINI (views.py) ===
    # print("\n" + "="*50)
    # print("🔍 DEBUGGING ORM: DAFTAR INDIKATOR TERFILTER")
    # print("="*50)
    # for komponen in komponen_list:
    #     print(f"🔹 Domain: {komponen.kode_komponen} - {komponen.nama_komponen}")
    #     for sub in komponen.sub_komponen.all():
    #         print(f"   ├─ Sub-Komponen: {sub.kode_komponen} - {sub.nama_komponen}")
    #         # Mengakses indikator_list yang sudah di-prefetch & filter
    #         for ind in sub.indikator_list.all():
    #             print(f"   │  └─ [ID: {ind.id}] Indikator {ind.nomor_indikator}")
    # print("="*50 + "\n")
    # ===============================

    return render(request, "evaluasi/kuesioner_form.html", context)


# ==============================================================================
# 4. VIEWS PENDUKUNG: JALUR VERIFIKASI SUPERVISOR (AUDITED & SINKRON)
# ==============================================================================
@login_required(login_url="login")
@role_required(allowed_roles=["SUPERVISOR"])
def verifikasi_list_view(request):
    user_profile = request.user.profile
    user_role = user_profile.role.upper()
 
    # --------------------------------------------------------------------------
    # ALUR A: PROSES EKSEKUSI TOMBOL AUDIT (POST METHOD WITH ACCESS FILTER)
    # --------------------------------------------------------------------------
    if request.method == "POST":
        transaksi_id = request.POST.get("transaksi_id")
        action = request.POST.get("action")
        catatan_supervisor = request.POST.get("catatan_supervisor", "").strip()
 
        transaksi = get_object_or_404(TransaksiEvaluasi, id=transaksi_id)
 
        # PROTEKSI EKSTRA: Pastikan supervisor tidak bisa bypass approve/reject indeks luar
        if user_role != "SUPERADMIN" and not user_profile.indeks_akses.filter(id=transaksi.indeks_aktif.id).exists():
            messages.error(request, "⛔ Anda tidak memiliki otoritas audit untuk jenis indeks ini!")
            return redirect("verifikasi_list")
 
        if action == "approve":
            pilihan_verifikasi_id = request.POST.get("pilihan_verifikasi_id", "").strip()
            nilai_angka_verifikasi = request.POST.get("nilai_angka_verifikasi", "").strip()
            transaksi.status = "VERIFIED"
            if catatan_supervisor:
                transaksi.catatan_supervisor = catatan_supervisor
 
            # Simpan pilihan_verifikasi berdasarkan tipe indikator
            if transaksi.indikator.tipe_penilaian == "INPUT_ANGKA" and nilai_angka_verifikasi:
                # Supervisor input nilai koreksi angka → buat/ambil PilihanJawaban dinamis
                try:
                    nilai_decimal = Decimal(nilai_angka_verifikasi)
                    pilihan_verif_obj, _ = PilihanJawabanIndikator.objects.get_or_create(
                        indikator=transaksi.indikator,
                        nilai_angka=nilai_decimal,
                        defaults={
                            "label_level": f"Nilai {nilai_decimal}",
                            "narasi_kriteria": f"Input angka verifikasi supervisor: {nilai_decimal}",
                        },
                    )
                    transaksi.pilihan_verifikasi = pilihan_verif_obj
                except Exception:
                    # Fallback ke pilihan mandiri jika nilai tidak valid
                    transaksi.pilihan_verifikasi = transaksi.pilihan_mandiri
            elif pilihan_verifikasi_id:
                # BERJENJANG/BINER: supervisor pilih level berbeda
                pilihan_verif_obj = get_object_or_404(PilihanJawabanIndikator, id=pilihan_verifikasi_id)
                transaksi.pilihan_verifikasi = pilihan_verif_obj
            else:
                # Default: sama dengan pilihan mandiri OPD
                transaksi.pilihan_verifikasi = transaksi.pilihan_mandiri
            transaksi.save()
            catat_aktivitas(
                request, "APPROVE",
                deskripsi=f"Approve Indikator {transaksi.indikator.nomor_indikator} milik {transaksi.opd_pengisi_terakhir.nama_opd} — {transaksi.indeks_aktif.kode_indeks}",
                indeks=transaksi.indeks_aktif,
                opd=transaksi.opd_pengisi_terakhir,
            )
            kirim_notifikasi_ke_operator(transaksi, "APPROVE")
            messages.success(request, f"✅ Sukses memverifikasi Indikator {transaksi.indikator.nomor_indikator} milik {transaksi.opd_pengisi_terakhir.nama_opd}.")
 
        elif action == "reject":
            transaksi.status = "DRAF"
            transaksi.catatan_supervisor = catatan_supervisor if catatan_supervisor else "Ditolak oleh Supervisor (Alasan tidak spesifik)."
            transaksi.save()
            catat_aktivitas(
                request, "REJECT",
                deskripsi=f"Tolak Indikator {transaksi.indikator.nomor_indikator} milik {transaksi.opd_pengisi_terakhir.nama_opd} — Alasan: {catatan_supervisor[:80]}",
                indeks=transaksi.indeks_aktif,
                opd=transaksi.opd_pengisi_terakhir,
            )
            kirim_notifikasi_ke_operator(transaksi, "REJECT")
            messages.warning(request, f"❌ Indikator {transaksi.indikator.nomor_indikator} milik {transaksi.opd_pengisi_terakhir.nama_opd} dikembalikan ke draf untuk revisi.")
 
        indeks_terpilih = request.GET.get('indeks', '')
        if indeks_terpilih:
            return redirect(f"/verifikasi/?indeks={indeks_terpilih}")
        
        return redirect(request.path_info)
 
    # --------------------------------------------------------------------------
    # ALUR B: PENYAJIAN DATA & FILTER DROPDOWN (GET METHOD RESTRICTED)
    # --------------------------------------------------------------------------
    # SINKRONISASI DROPDOWN: Hanya tampilkan indeks milik supervisor yang bersangkutan
    if user_role == "SUPERADMIN":
        semua_indeks = JenisIndeks.objects.all().order_by('kode_indeks')
    else:
        semua_indeks = user_profile.indeks_akses.all().order_by('kode_indeks')
    
    indeks_terpilih = request.GET.get("indeks", "")
    
    # ---- QUEUE: Menunggu Verifikasi (status SUBMITTED) ----
    query_ajuan = TransaksiEvaluasi.objects.filter(status="SUBMITTED").select_related(
        "indeks_aktif", "indikator", "pilihan_mandiri", "opd_pengisi_terakhir"
    ).prefetch_related("indikator__pilihan_jawaban")
    
    if user_role != "SUPERADMIN":
        query_ajuan = query_ajuan.filter(indeks_aktif__in=user_profile.indeks_akses.all())
    
    if indeks_terpilih and indeks_terpilih != "all":
        query_ajuan = query_ajuan.filter(indeks_aktif_id=indeks_terpilih)
    
    daftar_ajuan = query_ajuan.order_by("-indeks_aktif__kode_indeks", "indikator__nomor_indikator")
    
    # ---- RIWAYAT: Sudah Disahkan (VERIFIED) + Pernah Ditolak (DRAF + ada catatan supervisor) ----
    query_riwayat = TransaksiEvaluasi.objects.filter(
        Q(status="VERIFIED") |
        Q(status="DRAF", catatan_supervisor__isnull=False)
    ).exclude(
        catatan_supervisor=""
    ).select_related(
        "indeks_aktif", "indikator", "pilihan_mandiri", "pilihan_verifikasi", "opd_pengisi_terakhir", "user_updated_by"
    )
    
    if user_role != "SUPERADMIN":
        query_riwayat = query_riwayat.filter(indeks_aktif__in=user_profile.indeks_akses.all())
    
    if indeks_terpilih and indeks_terpilih != "all":
        query_riwayat = query_riwayat.filter(indeks_aktif_id=indeks_terpilih)
    
    daftar_riwayat = query_riwayat.order_by("-updated_at")  # Terbaru dulu
    
    indeks_terpilih_label = None
    if indeks_terpilih and indeks_terpilih != "all":
        indeks_obj_terpilih = semua_indeks.filter(id=indeks_terpilih).first()
        if indeks_obj_terpilih:
            indeks_terpilih_label = f"📊 {indeks_obj_terpilih.kode_indeks} - Th. {indeks_obj_terpilih.tahun_berlaku}"

    context = {
        "semua_indeks":    semua_indeks,
        "indeks_terpilih": indeks_terpilih,
        "daftar_ajuan":    daftar_ajuan,
        "daftar_riwayat":  daftar_riwayat,
        "indeks_terpilih_label": indeks_terpilih_label,
    }
    return render(request, "evaluasi/verifikasi_list.html", context)

# ==============================================================================
# HASIL INDEKS VIEW — Dual Mode: Nilai Sementara vs Nilai Sah
# ==============================================================================
@login_required(login_url="login")
@role_required(allowed_roles=["SUPERADMIN", "SUPERVISOR", "OPERATOR"])
def hasil_indeks_view(request, kode_indeks):
    indeks_aktif = get_object_or_404(JenisIndeks, kode_indeks=kode_indeks)
    user_profile = request.user.profile
    user_role = user_profile.role.upper()

    semua_opd = None
    opd_terpilih = None

    # Validasi akses indeks
    if user_role != "SUPERADMIN" and not user_profile.indeks_akses.filter(id=indeks_aktif.id).exists():
        messages.error(request, f"⛔ AKSES DITOLAK! Anda tidak terdaftar untuk indeks {kode_indeks}.")
        return redirect("dashboard")
    
    # Base filter kueri transaksi
    filters = {"indeks_aktif": indeks_aktif}

    if user_role in ["SUPERADMIN", "SUPERVISOR"]:
        semua_opd = OPD.objects.filter(
            transaksi_diisi__indeks_aktif=indeks_aktif
        ).distinct().order_by("nama_opd")
        
        opd_id = request.GET.get("opd_id", "all")
        if opd_id and opd_id != "all":
            opd_terpilih = get_object_or_404(OPD, id=opd_id)
            filters["opd_pengisi_terakhir"] = opd_terpilih 
    else:
        opd_terpilih = user_profile.opd
        filters["opd_pengisi_terakhir"] = opd_terpilih # 

    # Ambil data transaksi sesuai filter (Ganti "opd" menjadi "opd_pengisi_terakhir")
    semua_transaksi = TransaksiEvaluasi.objects.filter(**filters).select_related(
        "indikator__komponen__parent",
        "pilihan_mandiri",
        "pilihan_verifikasi",
        "opd_pengisi_terakhir"
    ).order_by("indikator__nomor_indikator", "-updated_at")

    # Mapping bobot
    bobot_map = {
        b.indikator_id: b.bobot_nilai
        for b in BobotIndikatorPeriode.objects.filter(jenis_indeks=indeks_aktif)
    }
    total_indikator = len(bobot_map)

    # Fungsi Pembangun Hierarki
    def bangun_hierarki(transaksi_qs, mode):
        hierarki = {}
        total_skor = Decimal("0")
        total_bobot = Decimal("0")
        jumlah_terisi = 0

        for tx in transaksi_qs:
            if mode == "sementara":
                pilihan = tx.pilihan_mandiri
                if not pilihan:
                    continue
            else: 
                pilihan = tx.pilihan_verifikasi
                if not pilihan or tx.status != "VERIFIED":
                    continue

            indikator = tx.indikator
            aspek = indikator.komponen
            domain = aspek.parent
            bobot = bobot_map.get(indikator.id, Decimal("0"))
            skor = pilihan.nilai_angka
            nilai_terbobot = (skor * bobot) / Decimal("100")

            domain_key = domain.id if domain else aspek.id
            domain_obj = domain if domain else aspek

            if domain_key not in hierarki:
                hierarki[domain_key] = {
                    "kode": domain_obj.kode_komponen,
                    "nama": domain_obj.nama_komponen,
                    "aspek_list": {},
                    "total_bobot": Decimal("0"),
                    "total_nilai_terbobot": Decimal("0"),
                }

            aspek_key = aspek.id
            if aspek_key not in hierarki[domain_key]["aspek_list"]:
                hierarki[domain_key]["aspek_list"][aspek_key] = {
                    "kode": aspek.kode_komponen,
                    "nama": aspek.nama_komponen,
                    "indikator_list": [],
                    "total_bobot": Decimal("0"),
                    "total_nilai_terbobot": Decimal("0"),
                }

            # 🛠️ KOREKSI DI SINI: Ambil dari relasi field baru
            opd_obj = tx.opd_pengisi_terakhir 

            hierarki[domain_key]["aspek_list"][aspek_key]["indikator_list"].append({
                "nomor": indikator.nomor_indikator,
                "nama": indikator.nama_indikator,
                "nama_opd": opd_obj.nama_opd if opd_obj else "-",
                "singkatan_opd": opd_obj.singkatan if opd_obj and opd_obj.singkatan else (opd_obj.nama_opd[:15] if opd_obj else "-"),
                "label_level": pilihan.label_level,
                "skor_mentah": skor,
                "bobot": bobot,
                "nilai_terbobot": round(nilai_terbobot, 4),
                "status": tx.status,
                "catatan_supervisor": tx.catatan_supervisor or "" if mode == "sah" else "",
                "sudah_verified": tx.status == "VERIFIED",
            })

            hierarki[domain_key]["aspek_list"][aspek_key]["total_bobot"] += bobot
            hierarki[domain_key]["aspek_list"][aspek_key]["total_nilai_terbobot"] += nilai_terbobot
            hierarki[domain_key]["total_bobot"] += bobot
            hierarki[domain_key]["total_nilai_terbobot"] += nilai_terbobot
            total_skor += nilai_terbobot
            total_bobot += bobot
            jumlah_terisi += 1

        # Sorting data hierarki
        for d in hierarki.values():
            d["nilai_domain"] = round(d["total_nilai_terbobot"], 4)
            d["total_bobot"] = round(d["total_bobot"], 2)
            for a in d["aspek_list"].values():
                a["nilai_aspek"] = round(a["total_nilai_terbobot"], 4)
                a["total_bobot"] = round(a["total_bobot"], 2)
                a["indikator_list"].sort(key=lambda x: x["nomor"])

        hierarki_list = sorted(hierarki.values(), key=lambda x: x["kode"])
        for d in hierarki_list:
            d["aspek_list"] = sorted(d["aspek_list"].values(), key=lambda x: x["kode"])

        return {
            "nilai_akhir": round(total_skor, 4),
            "total_bobot": round(total_bobot, 2),
            "jumlah_terisi": jumlah_terisi,
            "jumlah_total": total_indikator,
            "persen": round((jumlah_terisi / total_indikator * 100), 1) if total_indikator > 0 else 0,
            "hierarki": hierarki_list,
        }

    context = {
        "indeks_aktif": indeks_aktif,
        "semua_opd": semua_opd,
        "opd_terpilih": opd_terpilih,
        "hasil_sementara": bangun_hierarki(semua_transaksi, "sementara"),
        "hasil_sah": bangun_hierarki(semua_transaksi, "sah"),
        "tab_aktif": request.GET.get("tab", "sementara"),
        "user_role": user_role,
    }
    return render(request, "evaluasi/hasil_indeks.html", context)

# ==============================================================================
# 5. ENDPOINT AJAX POLLING: CEK PERUBAHAN DATA KUESIONER SECARA RINGAN
# ==============================================================================
@login_required(login_url="login")
@role_required(allowed_roles=["OPERATOR", "SUPERADMIN"])
def poll_kuesioner_view(request, kode_indeks):
    """
    Endpoint JSON ringan untuk AJAX polling di halaman kuesioner.
    Mengembalikan timestamp updated_at terbaru dari transaksi OPD ini.
    Dipanggil setiap 30 detik oleh JavaScript — jika ada perubahan,
    frontend akan menampilkan banner notifikasi tanpa memaksa reload.
    """
    indeks_aktif = get_object_or_404(JenisIndeks, kode_indeks=kode_indeks)
    user_profile = request.user.profile
    user_opd     = user_profile.opd
    user_role    = user_profile.role.upper()
    
    if user_role == "SUPERADMIN":
        bobot_assigned = BobotIndikatorPeriode.objects.filter(
            jenis_indeks=indeks_aktif
        ).values_list("indikator_id", flat=True)
    else:
        bobot_assigned = (
            BobotIndikatorPeriode.objects.filter(jenis_indeks=indeks_aktif)
            .filter(
                Q(opd_penanggung_jawab__isnull=True) | Q(opd_penanggung_jawab=user_opd)
            )
            .values_list("indikator_id", flat=True)
        )
 
    indikator_ids = list(bobot_assigned)
 
    transaksi_qs = TransaksiEvaluasi.objects.filter(
        indeks_aktif=indeks_aktif,
        indikator_id__in=indikator_ids,
    )
 
    # Ambil timestamp terbaru — satu query ringan dengan MAX aggregation
    hasil = transaksi_qs.aggregate(latest=Max("updated_at"))
    latest_ts = hasil["latest"]
 
    # Hitung juga jumlah terisi untuk sinkronisasi progress bar
    total     = len(indikator_ids)
    terisi    = transaksi_qs.filter(pilihan_mandiri__isnull=False).count()
 
    # Serialisasi timestamp ke ISO 8601 agar mudah dibandingkan di JavaScript
    return JsonResponse({
        "status":    "ok",
        "latest_ts": latest_ts.isoformat() if latest_ts else None,
        "total":     total,
        "terisi":    terisi,
    })

# =============================================================================
# Masih belum ada keperluan dibuat, tapi endpoint ini disiapkan untuk manajemen master data indikator di masa depan (CRUD indikator, bobot, dll) — hanya bisa diakses SUPERADMIN
# =============================================================================
@login_required(login_url="login")
@role_required(allowed_roles=["SUPERADMIN"])
def master_indikator_view(request):
    return render(request, "evaluasi/master_indicators.html")

# ==============================================================================
# ACTIVITY LOG VIEW — Superadmin lihat semua, Supervisor lihat OPD-nya
# ==============================================================================
@login_required(login_url="login")
@role_required(allowed_roles=["SUPERVISOR"])
def activity_log_view(request):
    user_profile = request.user.profile
    user_role    = user_profile.role.upper()

    logs = ActivityLog.objects.select_related("user", "user__profile", "opd", "indeks")

    # ---------- Filter hak akses ----------
    opd_ids_terkait  = []
    if user_role == "SUPERVISOR":
        # Supervisor: hanya lihat log operator dari OPD yang ada di indeks aksesnya
        indeks_akses     = user_profile.indeks_akses.all()
        opd_ids_terkait  = (
            TransaksiEvaluasi.objects
            .filter(indeks_aktif__in=indeks_akses)
            .values_list("opd_pengisi_terakhir_id", flat=True)
            .distinct()
        )
        logs = logs.filter(
            user__profile__role="OPERATOR",
            opd_id__in=opd_ids_terkait,
        )

    # ---------- Filter tambahan dari query string ----------
    filter_aksi  = request.GET.get("aksi", "")
    filter_opd   = request.GET.get("opd", "")
    filter_user  = request.GET.get("user", "")
    filter_nip   = request.GET.get("nip", "")

    if filter_aksi:
        logs = logs.filter(aksi=filter_aksi)
    if filter_opd:
        logs = logs.filter(opd_id=filter_opd)
    if filter_user:
        logs = logs.filter(user__username__icontains=filter_user)
    if filter_nip:
        logs = logs.filter(user__profile__nip__icontains=filter_nip)

    logs = logs[:200]  # Batasi 200 entri terbaru

    # Data untuk dropdown filter
    if user_role == "SUPERADMIN":
        semua_opd = OPD.objects.all().order_by("nama_opd")
    else:
        semua_opd = OPD.objects.filter(id__in=opd_ids_terkait).order_by("nama_opd")

    semua_aksi = ActivityLog.AKSI_CHOICES

    context = {
        "logs":        logs,
        "semua_opd":   semua_opd,
        "semua_aksi":  semua_aksi,
        "filter_aksi": filter_aksi,
        "filter_opd":  filter_opd,
        "filter_user": filter_user,
        "filter_nip":  filter_nip,
        "user_role":   user_role,
    }
    return render(request, "evaluasi/activity_log.html", context)

# ==============================================================================
# NOTIFIKASI VIEW & ENDPOINT AJAX
# ==============================================================================
@login_required(login_url="login")
def notifikasi_fetch_view(request):
    """
    AJAX endpoint — kembalikan max 20 notifikasi terbaru user yang login.
    Dipanggil saat user klik bell icon untuk membuka dropdown.
    """
    notif_qs = Notifikasi.objects.filter(
        penerima=request.user
    ).select_related("indeks", "transaksi__indikator")[:20]
 
    data = []
    for n in notif_qs:
        waktu_lokal = timezone.localtime(n.created_at)
        data.append({
            "id":           n.id,
            "tipe":         n.tipe,
            "judul":        n.judul,
            "pesan":        n.pesan,
            "sudah_dibaca": n.sudah_dibaca,
            "kode_indeks":  n.indeks.kode_indeks,
            "created_at":   waktu_lokal.strftime("%d %b %Y, %H:%M WIB"),
        })
 
    return JsonResponse({"status": "ok", "notifikasi": data}) 
 
@login_required(login_url="login")
def notifikasi_baca_view(request):
    """
    AJAX endpoint POST — tandai notifikasi sebagai sudah dibaca.
    Kirim { "notif_id": <id> } untuk satu notif, atau { "semua": true } untuk bulk.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)
 
    import json
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"status": "error", "msg": "Invalid JSON"}, status=400)
 
    if body.get("semua"):
        Notifikasi.objects.filter(penerima=request.user, sudah_dibaca=False).update(sudah_dibaca=True)
    else:
        notif_id = body.get("notif_id")
        if notif_id:
            Notifikasi.objects.filter(id=notif_id, penerima=request.user).update(sudah_dibaca=True)
 
    unread_count = Notifikasi.objects.filter(penerima=request.user, sudah_dibaca=False).count()
    return JsonResponse({"status": "ok", "unread_count": unread_count})
 
 
@login_required(login_url="login")
def notifikasi_poll_view(request):
    """
    AJAX endpoint ringan — hanya kembalikan jumlah notif belum dibaca.
    Dipanggil setiap 30 detik oleh JS di base.html untuk update badge bell.
    """
    count = Notifikasi.objects.filter(penerima=request.user, sudah_dibaca=False).count()
    return JsonResponse({"status": "ok", "unread_count": count})