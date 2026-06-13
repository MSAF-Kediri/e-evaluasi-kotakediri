from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.contrib.sessions.models import Session

class ProfileUser(models.Model):
    # Definisi pilihan role secara native
    ROLE_CHOICES = [
        ('SUPERADMIN', 'Superadmin'),
        ('SUPERVISOR', 'Supervisor (Tim Verifikator)'),
        ('OPERATOR', 'Operator (Perwakilan OPD)'),
    ]

    JENIS_KELAMIN_CHOICES = [
        ('L', 'Laki-laki'),
        ('P', 'Perempuan'),
    ]
        
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    nama_lengkap = models.CharField(max_length=150, verbose_name="Nama Lengkap & Gelar")
    opd = models.CharField(max_length=150, verbose_name="OPD / Instansi")
    nip = models.CharField(max_length=50, unique=True, verbose_name="NIP")
    no_hp = models.CharField(max_length=20, verbose_name="No HP")
    jabatan = models.CharField(max_length=100, verbose_name="Jabatan")
    jenis_kelamin = models.CharField(
        max_length=1, 
        choices=JENIS_KELAMIN_CHOICES, 
        blank=True, 
        null=True, 
        verbose_name="Jenis Kelamin"
    )

    # Kolom role native kita
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='OPERATOR', verbose_name="Hak Akses / Role")

    # KETENTUAN BARU: Pengendali Blokir Akun Native
    salah_login_count = models.IntegerField(default=0, verbose_name="Jumlah Salah Login")
    is_active_sw = models.BooleanField(default=True, verbose_name="Akun Aktif (Software)")

    # PENGUNCI SESI: Menyimpan ID Sesi aktif terakhir untuk batasan 1 browser
    last_session_key = models.CharField(max_length=40, blank=True, null=True, verbose_name="ID Sesi Terakhir")

    def __str__(self):
        return f"{self.nama_lengkap} - {self.role} ({self.opd})"
    
class JenisIndeks(models.Model):
    kode_indeks = models.CharField(max_length=20, unique=True, verbose_name="Kode Indeks (e.g., PEMDI, SPBE)")
    nama_indeks = models.CharField(max_length=255, verbose_name="Nama Panjang Indeks")
    tahun_berlaku = models.IntegerField(default=2026, verbose_name="Tahun Berlaku")
    keterangan = models.TextField(blank=True, null=True, verbose_name="Keterangan / Dasar Hukum")

    def __str__(self):
        return f"{self.kode_indeks} ({self.tahun_berlaku})"

    class Meta:
        verbose_name_plural = "1. Master Jenis Indeks"

class KomponenEvaluasi(models.Model):
    TIPE_CHOICES = [
        ('DOMAIN', 'Domain / Rumpun Atas'),
        ('ASPEK', 'Aspek Penilaian'),
        ('LAINNYA', 'Tipe Kustom Lainnya'),
    ]

    indeks = models.ForeignKey(JenisIndeks, on_delete=models.CASCADE, related_name='komponen_list', verbose_name="Jenis Indeks")
    
    # SELF-REFERENCE: Menunjuk ke komponen induknya sendiri di tabel yang sama
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='sub_komponen', verbose_name="Induk Komponen (Parent)")
    
    tipe = models.CharField(max_length=20, choices=TIPE_CHOICES, default='ASPEK', verbose_name="Tipe Struktur")
    kode_komponen = models.CharField(max_length=10, verbose_name="Kode (e.g., D1, A1)")
    nama_komponen = models.CharField(max_length=255, verbose_name="Nama Komponen")

    def __str__(self):
        prefix = f"[{self.tipe}] "
        if self.parent:
            prefix += f"Sub dari {self.parent.kode_komponen} -> "
        return f"[{self.indeks.kode_indeks}] {prefix} {self.kode_komponen} - {self.nama_komponen}"

    class Meta:
        verbose_name_plural = "2. Master Struktur Komponen"

class IndikatorEvaluasi(models.Model):
    komponen = models.ForeignKey(KomponenEvaluasi, on_delete=models.CASCADE, related_name='indikator_list', verbose_name="Aspek Penilaian")
    nomor_indikator = models.IntegerField(verbose_name="Nomor Indikator")
    nama_indikator = models.CharField(max_length=255, verbose_name="Nama Indikator")
    penjelasan = models.TextField(blank=True, null=True, verbose_name="Penjelasan / Definisi")
    
    # KETENTUAN BARU: Kita tambahkan flag tipe penilaian agar sistem tahu cara merendernya di frontend
    TIPE_PENILAIAN_CHOICES = [
        ('BERJENJANG', 'Pilihan Berjenjang / Level (e.g., Level 1-5)'),
        ('BINER', 'Ya / Tidak'),
        ('INPUT_ANGKA', 'Input Angka / Persentase Manual'),
    ]
    tipe_penilaian = models.CharField(max_length=20, choices=TIPE_PENILAIAN_CHOICES, default='BERJENJANG', verbose_name="Tipe Penilaian")

    def __str__(self):
        return f"[{self.komponen.indeks.kode_indeks}] Indikator {self.nomor_indikator}: {self.nama_indikator}"

    class Meta:
        unique_together = ('komponen', 'nomor_indikator')
        verbose_name_plural = "3. Master Indikator"


class PilihanJawabanIndikator(models.Model):
    # Relasi ke Indikator: Satu indikator bisa punya banyak pilihan level jawaban
    indikator = models.ForeignKey(IndikatorEvaluasi, on_delete=models.CASCADE, related_name='pilihan_jawaban', verbose_name="Indikator")
    
    nilai_angka = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Nilai (Angka/Skor)")
    label_level = models.CharField(max_length=50, verbose_name="Label (e.g., Level 1, Ya, Kurang)")
    narasi_kriteria = models.TextField(verbose_name="Narasi Kriteria / Penjelasan Detail Jawaban")

    def __str__(self):
        return f"{self.indikator.komponen.indeks.kode_indeks} - Indikator {self.indikator.nomor_indikator} [Skor {self.nilai_angka}]"

    class Meta:
        ordering = ['nilai_angka'] # Mengurutkan pilihan dari nilai terendah ke tertinggi otomatis
        verbose_name_plural = "4. Master Pilihan Jawaban Indikator"

# ================= TABEL BARU: TRANSAKSI ISIAN MANDIRI OPD =================
class TransaksiEvaluasi(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft (Belum Dikirim)'),
        ('SUBMITTED', 'Diajukan ke Kominfo'),
        ('VERIFIED', 'Selesai Diverifikasi'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hasil_evaluasi', verbose_name="Operator OPD")
    indikator = models.ForeignKey(IndikatorEvaluasi, on_delete=models.CASCADE, related_name='transaksi_list', verbose_name="Indikator")
    pilihan_mandiri = models.ForeignKey(PilihanJawabanIndikator, on_delete=models.SET_NULL, null=True, blank=True, related_name='pilihan_opd', verbose_name="Jawaban Mandiri")
    link_bukti_dukung = models.URLField(max_length=500, blank=True, null=True, verbose_name="Link Bukti Dukung (Drive/Cloud)")
    catatan_opd = models.TextField(blank=True, null=True, verbose_name="Penjelasan/Catatan dari OPD")

    # Kolom Khusus Verifikator (Kominfo)
    pilihan_verifikasi = models.ForeignKey(PilihanJawabanIndikator, on_delete=models.SET_NULL, null=True, blank=True, related_name='pilihan_verifikator', verbose_name="Jawaban Hasil Verifikasi")
    catatan_verifikator = models.TextField(blank=True, null=True, verbose_name="Catatan/Rekomendasi Auditor")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="Status Dokumen")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'indikator')
        verbose_name_plural = "5. Transaksi Evaluasi Mandiri"

    def __str__(self):
        return f"{self.user.username} - Indikator {self.indikator.nomor_indikator} [{self.status}]"


# ================= SIGNAL MANAGEMENT: SINGLE ACTIVE SESSION =================
@receiver(user_logged_in)
def batasi_satu_session_browser(sender, request, user, **kwargs):
    if hasattr(user, 'profile'):
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