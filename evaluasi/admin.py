from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from .models import (
    OPD,
    ProfileUser,
    JenisIndeks,
    KomponenEvaluasi,
    IndikatorEvaluasi,
    PilihanJawabanIndikator,
    TransaksiEvaluasi,
    BobotIndikatorPeriode,
)
from django.contrib.admin.models import LogEntry


# Definisikan Resource untuk pemetaan kolom Excel/CSV
class OPDResource(resources.ModelResource):
    class Meta:
        model = OPD
        # Tentukan kolom apa saja yang bisa diimport/export
        fields = ("id", "kode_opd", "nama_opd", "singkatan")
        # Gunakan 'kode_opd' atau 'nama_opd' sebagai kunci unik saat import agar tidak terjadi duplikasi data
        import_id_fields = ["kode_opd"]


@admin.register(OPD)
class OPDAdmin(ImportExportModelAdmin):
    resource_classes = [OPDResource]
    list_display = ["kode_opd", "nama_opd", "singkatan"]
    search_fields = ["nama_opd", "kode_opd"]
    list_per_page = 20


# ==============================================================================
# 1. PROFILE USER ADMIN
# ==============================================================================
@admin.register(ProfileUser)
class ProfileUserAdmin(admin.ModelAdmin):
    list_display = (
        "get_username",
        "nama_lengkap",
        "jenis_kelamin",
        "role",
        "opd",
        "is_active_sw",
        "salah_login_count",
    )
    list_per_page = 25
    search_fields = ("user__username", "nama_lengkap", "opd", "nip", "no_hp", "jabatan")
    list_filter = ("role", "jenis_kelamin", "opd")
    list_editable = ("is_active_sw", "role")
    
    # Widget dual-list box box untuk mempermudah memilih banyak indeks sekaligus
    filter_horizontal = ("indeks_akses",)


    def get_username(self, obj):
        return obj.user.username

    get_username.short_description = "Username Login"


# ==============================================================================
# 2. TABEL PENGATURAN BOBOT PERIODE (INLINE DI DALAM JENIS INDEKS)
# ==============================================================================
class BobotIndikatorInline(admin.TabularInline):
    model = BobotIndikatorPeriode
    extra = 1
    autocomplete_fields = ["indikator"]
    filter_horizontal = ("opd_penanggung_jawab",)


@admin.register(JenisIndeks)
class JenisIndeksAdmin(admin.ModelAdmin):
    list_display = ("kode_indeks", "nama_indeks", "tahun_berlaku")
    search_fields = ("kode_indeks", "nama_indeks")
    list_filter = ("tahun_berlaku",)
    list_per_page = 25
    inlines = [BobotIndikatorInline]


# ==============================================================================
# 3. BANK STRUKTUR KOMPONEN ADMIN (BEBAS EROR)
# ==============================================================================
@admin.register(KomponenEvaluasi)
class KomponenEvaluasiAdmin(admin.ModelAdmin):
    list_display = ("kode_komponen", "nama_komponen", "tipe", "parent")
    search_fields = ("kode_komponen", "nama_komponen")
    list_filter = ("tipe", "parent")
    list_per_page = 25

# ==============================================================================
# 4. BANK INDIKATOR & PILIHAN JAWABAN LEVEL 1-5 ADMIN (PERBAIKAN FITUR FILTER)
# ==============================================================================
class PilihanJawabanInline(admin.TabularInline):
    model = PilihanJawabanIndikator
    extra = 5
    min_num = 1


@admin.register(IndikatorEvaluasi)
class IndikatorEvaluasiAdmin(admin.ModelAdmin):
    list_display = (
        "nomor_indikator",
        "nama_indikator",
        "tipe_penilaian",
        "get_komponen",
    )
    search_fields = ("nomor_indikator", "nama_indikator")

    # SOLUSI ALTERNATIF: Fokus menyaring berdasarkan tipe penilaian dan rumpun komponen
    list_filter = ("tipe_penilaian", "komponen")
    list_per_page = 25

    inlines = [PilihanJawabanInline]

    def get_komponen(self, obj):
        return obj.komponen.nama_komponen

    get_komponen.short_description = "Aspek"


# ==============================================================================
# 5. TRANSAKSI EVALUASI MANDIRI
# ==============================================================================
@admin.register(TransaksiEvaluasi)
class TransaksiEvaluasiAdmin(admin.ModelAdmin):
    list_display = [
        'opd_pengisi_terakhir', 
        'indeks_aktif', 
        'indikator', 
        'pilihan_mandiri', 
        'status',
        'pilihan_verifikasi',
        'catatan_supervisor',
        'user_updated_by', 
        'updated_at'
    ]
    
    list_filter = [
        'indeks_aktif', 
        'status', 
        'pilihan_verifikasi',
        'opd_pengisi_terakhir',              
        'created_at'
    ]
    
    search_fields = [
        'opd_pengisi_terakhir__nama_opd', 
        'opd_pengisi_terakhir__singkatan', 
        'indikator__nama_indikator', 
        'indikator__nomor_indikator'
    ]
    
    ordering = ['indeks_aktif', 'opd_pengisi_terakhir', 'indikator__nomor_indikator']
    list_per_page = 30

# ==============================================================================
# 6. LOG AKTIVITAS PENGGUNA (READ-ONLY)
# ==============================================================================
@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ['action_time', 'user', 'content_type', 'object_repr', 'action_flag', 'change_message']
    list_filter = ['action_flag', 'content_type']
    search_fields = ['user__username', 'object_repr']
    readonly_fields = [f.name for f in LogEntry._meta.fields]
    list_per_page = 25

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False