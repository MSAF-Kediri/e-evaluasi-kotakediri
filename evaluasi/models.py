from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.contrib.sessions.models import Session


# ==============================================================================
# MASTER DATA ORGANISASI (OPD)
# ==============================================================================
class OPD(models.Model):
    nama_opd = models.CharField(
        max_length=150,
        verbose_name="Nama OPD",
        unique=True,
        help_text="Contoh: Dinas Komunikasi dan Informatika",
    )
    kode_opd = models.CharField(
        max_length=50,
        verbose_name="Kode OPD",
        unique=True,
        help_text="Contoh: DISKOMINFO",
    )
    singkatan = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name="Singkatan",
        help_text="Contoh: Kominfo",
    )

    class Meta:
        verbose_name = "Master OPD"
        verbose_name_plural = "Master OPD"
        ordering = ["nama_opd"]

    def __str__(self):
        return self.nama_opd


# ==============================================================================
# AKUN & PROFILE USER
# ==============================================================================
class ProfileUser(models.Model):
    ROLE_CHOICES = [
        ("SUPERADMIN", "Superadmin"),
        ("SUPERVISOR", "Supervisor (Tim Verifikator)"),
        ("OPERATOR", "Operator (Perwakilan OPD)"),
    ]
    JENIS_KELAMIN_CHOICES = [
        ("L", "Laki-laki"),
        ("P", "Perempuan"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    nama_lengkap = models.CharField(max_length=150, verbose_name="Nama Lengkap & Gelar")
    opd = models.ForeignKey(
        OPD,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pegawai_opd",
        verbose_name="Instansi/OPD",
        help_text="Pilih Instansi/OPD tempat pegawai ini bertugas",
    )
    # --- KOLOM BARU UNTUK HAK AKSES INDEKS ---
    indeks_akses = models.ManyToManyField(
        'JenisIndeks',
        blank=True,
        related_name="user_diizinkan",
        verbose_name="Akses Jenis Indeks",
        help_text="Pilih jenis indeks yang boleh diisi (Operator) atau disupervisi (Supervisor) oleh user ini. Kosongkan jika Superadmin memiliki semua akses."
    )
    # ----------------------------------------
    nip = models.CharField(max_length=50, unique=True, verbose_name="NIP")
    no_hp = models.CharField(max_length=20, verbose_name="No HP")
    email = models.EmailField(
        max_length=255, blank=True, null=True, verbose_name="Email"
    )
    jabatan = models.CharField(max_length=100, verbose_name="Jabatan")
    jenis_kelamin = models.CharField(
        max_length=1,
        choices=JENIS_KELAMIN_CHOICES,
        blank=True,
        null=True,
        verbose_name="Jenis Kelamin",
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="OPERATOR",
        verbose_name="Hak Akses / Role",
    )
    salah_login_count = models.IntegerField(
        default=0, verbose_name="Jumlah Salah Login"
    )
    is_active_sw = models.BooleanField(
        default=True, verbose_name="Akun Aktif (Software)"
    )
    last_session_key = models.CharField(
        max_length=40, blank=True, null=True, verbose_name="ID Sesi Terakhir"
    )

    def __str__(self):
        return f"{self.nama_lengkap} - {self.role} ({self.opd})"


# ==============================================================================
# 2. MASTER PERIODE / TARGET TAHUN EVALUASI (UBAHAN UTAMA OPSI B)
# ==============================================================================
class JenisIndeks(models.Model):
    kode_indeks = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Kode Indeks (e.g., SPBE-2025, SPBE-2026)",
    )
    nama_indeks = models.CharField(max_length=255, verbose_name="Nama Panjang Indeks")
    tahun_berlaku = models.IntegerField(default=2026, verbose_name="Tahun Berlaku")
    keterangan = models.TextField(
        blank=True, null=True, verbose_name="Keterangan / Dasar Hukum"
    )

    # KUNCI UTAMA: Penjaring dinamis Many-to-Many langsung ke Bank Indikator
    # Satu indikator abadi bisa dipakai di SPBE 2025, SPBE 2026, dst.
    indikator_diujikan = models.ManyToManyField(
        "IndikatorEvaluasi",
        through="BobotIndikatorPeriode",  # <-- Mengunci tabel penghubung kustom
        related_name="indeks_terkait",
        blank=True,
        verbose_name="Daftar Indikator yang Diujikan pada Periode Ini",
    )

    def __str__(self):
        return f"{self.kode_indeks} ({self.tahun_berlaku})"

    class Meta:
        verbose_name_plural = "1. Master Jenis Indeks (Periode)"


# ==============================================================================
# TABEL BARU (JUNCTION): MENGUNCI BOBOT INDIKATOR PER PERIODE TAHUN EVALUASI
# ==============================================================================
class BobotIndikatorPeriode(models.Model):
    jenis_indeks = models.ForeignKey(JenisIndeks, on_delete=models.CASCADE)
    indikator = models.ForeignKey("IndikatorEvaluasi", on_delete=models.CASCADE)
    bobot_nilai = models.DecimalField(max_digits=5, decimal_places=2)

    # Mengunci hak akses pengisian indikator ke OPERATOR OPD tertentu secara dinamis per periode.
    # Jika dikosongkan (blank=True), artinya indikator ini bersifat UMUM (wajib diisi seluruh OPD).
    opd_penanggung_jawab = models.ManyToManyField(
        OPD,
        blank=True,
        related_name="bobot_indikator_assigned",
        help_text="Kosongkan jika indikator ini bersifat UMUM untuk semua OPD pada periode ini.",
    )

    class Meta:
        unique_together = ("jenis_indeks", "indikator")
        verbose_name = "Pengaturan Bobot & Hak Akses Indikator"
        verbose_name_plural = "Pengaturan Bobot & Hak Akses Indikator"

    def __str__(self):
        return f"{self.jenis_indeks.kode_indeks} - {self.indikator.nomor_indikator} (Bobot: {self.bobot_nilai}%)"


# ==============================================================================
# 3. BANK DATA STRUKTUR HIERARKI ABADI (BEBAS HINGGA L1, L2, Ln)
# ==============================================================================
class KomponenEvaluasi(models.Model):
    TIPE_CHOICES = [
        ("DOMAIN", "Domain / Rumpun Atas"),
        ("ASPEK", "Aspek Penilaian"),
        ("LAINNYA", "Tipe Kustom Lainnya"),
    ]

    # SEKARANG BEBAS DARI INDEKS: Dihapus relasi ForeignKey ke JenisIndeks agar strukturnya abadi
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_komponen",
        verbose_name="Induk Komponen (Parent)",
    )
    tipe = models.CharField(
        max_length=20,
        choices=TIPE_CHOICES,
        default="ASPEK",
        verbose_name="Tipe Struktur",
    )
    kode_komponen = models.CharField(
        max_length=10, verbose_name="Kode (e.g., D1, A1, L1)"
    )
    nama_komponen = models.CharField(max_length=255, verbose_name="Nama Komponen")

    def __str__(self):
        # Jalur pelacakan teks hierarki ke atas agar mudah dibaca di Django Admin
        full_path = f"{self.kode_komponen} - {self.nama_komponen}"
        current_parent = self.parent
        while current_parent is not None:
            full_path = f"{current_parent.kode_komponen} - {full_path}"
            current_parent = current_parent.parent
        return f"[{self.tipe}] {full_path}"

    class Meta:
        verbose_name_plural = "2. Bank Struktur Komponen"


# ==============================================================================
# 4. BANK DATA INDIKATOR & MASTER PILIHAN JAWABAN ABADI
# ==============================================================================
class IndikatorEvaluasi(models.Model):
    # Mengunci ke tingkat komponen terdalam (bisa Aspek, L1, L2, atau Ln)
    komponen = models.ForeignKey(
        KomponenEvaluasi,
        on_delete=models.CASCADE,
        related_name="indikator_list",
        verbose_name="Struktur Komponen Terdalam",
    )
    nomor_indikator = models.IntegerField(verbose_name="Nomor Indikator")
    nama_indikator = models.CharField(max_length=255, verbose_name="Nama Indikator")
    penjelasan = models.TextField(
        blank=True, null=True, verbose_name="Penjelasan / Definisi"
    )

    TIPE_PENILAIAN_CHOICES = [
        ("BERJENJANG", "Pilihan Berjenjang / Level (e.g., Level 1-5)"),
        ("BINER", "Ya / Tidak"),
        ("INPUT_ANGKA", "Input Angka / Persentase Manual"),
    ]
    tipe_penilaian = models.CharField(
        max_length=20,
        choices=TIPE_PENILAIAN_CHOICES,
        default="BERJENJANG",
        verbose_name="Tipe Penilaian",
    )

    def __str__(self):
        return f"Indikator {self.nomor_indikator}: {self.nama_indikator} (Sub dari {self.komponen.kode_komponen})"

    class Meta:
        unique_together = ("komponen", "nomor_indikator")
        verbose_name_plural = "3. Bank Indikator Utama"


class PilihanJawabanIndikator(models.Model):
    indikator = models.ForeignKey(
        IndikatorEvaluasi,
        on_delete=models.CASCADE,
        related_name="pilihan_jawaban",
        verbose_name="Indikator",
    )
    nilai_angka = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Nilai (Angka/Skor)"
    )
    label_level = models.CharField(
        max_length=50, verbose_name="Label (e.g., Level 1, Ya, Kurang)"
    )
    narasi_kriteria = models.TextField(
        verbose_name="Narasi Kriteria / Penjelasan Detail Jawaban"
    )

    def __str__(self):
        return f"Ind {self.indikator.nomor_indikator} - [{self.label_level}] Skor {self.nilai_angka}"

    class Meta:
        ordering = ["nilai_angka"]
        verbose_name_plural = "4. Bank Pilihan Jawaban Indikator"


# ==============================================================================
# 5. TRANSAKSI ISIAN MANDIRI OPD (PENGUNCIAN MULTI-YEARS AMAN)
# ==============================================================================
class TransaksiEvaluasi(models.Model):
    STATUS_CHOICES = [
        ("DRAF", "Draf (Belum Dikirim)"),
        ("SUBMITTED", "Diajukan ke Supervisor"),
        ("VERIFIED", "Selesai Diverifikasi"),
    ]

    # KUNCI UTAMA 1: Ubah relasi dari User ke OPD agar lembar kerja dimiliki bersama oleh Instansi
    opd = models.ForeignKey(
        OPD,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="hasil_evaluasi_opd",
        verbose_name="Instansi / OPD Pengisi",
    )

    # Kolom audit opsional: Mengetahui siapa personil/operator terakhir yang menyentuh draf ini
    user_updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_transaksi",
        verbose_name="Operator Pengubah Terakhir",
    )

    # Menyimpan relasi ke JenisIndeks periode tahun berjalan
    indeks_aktif = models.ForeignKey(
        JenisIndeks,
        on_delete=models.CASCADE,
        related_name="transaksi_indeks_list",
        verbose_name="Periode Evaluasi",
    )

    indikator = models.ForeignKey(
        IndikatorEvaluasi,
        on_delete=models.CASCADE,
        related_name="transaksi_list",
        verbose_name="Indikator",
    )
    
    pilihan_mandiri = models.ForeignKey(
        PilihanJawabanIndikator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pilihan_opd",
        verbose_name="Jawaban Mandiri",
    )
    
    link_bukti_dukung = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Link Bukti Dukung (Drive/Cloud)",
    )
    
    catatan_opd = models.TextField(
        blank=True, null=True, verbose_name="Penjelasan/Catatan dari OPD"
    )

    # Kolom Khusus Verifikator (Kominfo)
    pilihan_verifikasi = models.ForeignKey(
        PilihanJawabanIndikator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pilihan_verifikator",
        verbose_name="Jawaban Hasil Verifikasi",
    )
    
    catatan_supervisor = models.TextField(
        blank=True, null=True, verbose_name="Catatan/Rekomendasi Supervisor"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAF", # Koreksi typo dari "DRAFT" agar konsisten dengan pilihan status
        verbose_name="Status Dokumen",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # KUNCI UTAMA 2: Satu OPD hanya boleh memiliki SATU data per indikator di setiap periode tahunan
        unique_together = ("opd", "indeks_aktif", "indikator")
        verbose_name_plural = "Transaksi Evaluasi Mandiri"

    def __str__(self):
        return f"{self.opd.singkatan or self.opd.nama_opd} - {self.indeks_aktif.kode_indeks} - Indikator {self.indikator.nomor_indikator} [{self.status}]"

# ==============================================================================
# 6. SIGNAL MANAGEMENT: SINGLE ACTIVE SESSION (RETAINED)
# ==============================================================================
@receiver(user_logged_in)
def batasi_satu_session_browser(sender, request, user, **kwargs):
    if hasattr(user, "profile"):
        profile = user.profile
        session_key_baru = request.session.session_key

        if profile.last_session_key and profile.last_session_key != session_key_baru:
            try:
                sesi_lama = Session.objects.get(session_key=profile.last_session_key)
                sesi_lama.delete()
            except Session.DoesNotExist:
                pass

        profile.last_session_key = session_key_baru
        profile.save()

# ==============================================================================
# 7. ACTIVITY LOG — JEJAK AKTIVITAS SELURUH PENGGUNA SISTEM
# ==============================================================================
class ActivityLog(models.Model):
    AKSI_CHOICES = [
        ("LOGIN",           "Login ke Sistem"),
        ("LOGOUT",          "Logout dari Sistem"),
        ("SIMPAN_JAWABAN",  "Simpan / Update Jawaban Kuesioner"),
        ("HAPUS_JAWABAN",   "Hapus Jawaban Kuesioner"),
        ("SUBMIT",          "Submit Kuesioner ke Supervisor"),
        ("APPROVE",         "Approve / Verifikasi Jawaban"),
        ("REJECT",          "Tolak / Kembalikan ke Draf"),
        ("GANTI_PASSWORD",  "Ganti Password"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activity_logs", verbose_name="Pengguna",
    )
    opd = models.ForeignKey(
        OPD, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activity_logs", verbose_name="OPD Terkait",
    )
    aksi = models.CharField(max_length=30, choices=AKSI_CHOICES, verbose_name="Jenis Aktivitas")
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Detail Aktivitas")
    indeks = models.ForeignKey(
        JenisIndeks, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activity_logs", verbose_name="Indeks Terkait",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP Address")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        ordering = ["-created_at"]

    def __str__(self):
        user_str = self.user.username if self.user else "?"
        return f"[{self.aksi}] {user_str} — {self.created_at.strftime('%d/%m/%Y %H:%M')}"
