from django.contrib import admin
from .models import ProfileUser, JenisIndeks, KomponenEvaluasi, IndikatorEvaluasi, PilihanJawabanIndikator

@admin.register(ProfileUser)
class ProfileUserAdmin(admin.ModelAdmin):
    # Tampilkan kolom status aktif dan jumlah salah login di tabel daftar
    list_display = ('get_username', 'nama_lengkap', 'jenis_kelamin', 'role', 'opd', 'is_active_sw', 'salah_login_count')
    search_fields = ('user__username', 'nama_lengkap', 'opd', 'nip', 'no_hp', 'jabatan')
    list_filter = ('role', 'jenis_kelamin', 'opd')
    
    # Berikan fitur edit instan (tinggal klik centang langsung aktif/blokir dari tabel daftar)
    list_editable = ('is_active_sw', 'role')

    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = 'Username Login'

@admin.register(JenisIndeks)
class JenisIndeksAdmin(admin.ModelAdmin):
    list_display = ('kode_indeks', 'nama_indeks', 'tahun_berlaku')
    search_fields = ('kode_indeks', 'nama_indeks')
    list_filter = ('tahun_berlaku',)

@admin.register(KomponenEvaluasi)
class KomponenEvaluasiAdmin(admin.ModelAdmin):
    list_display = ('kode_komponen', 'nama_komponen', 'tipe', 'parent', 'indeks')
    search_fields = ('kode_komponen', 'nama_komponen')
    list_filter = ('indeks', 'tipe', 'parent')

# 1. Buat struktur form inline untuk pilihan jawaban
class PilihanJawabanInline(admin.TabularInline):
    model = PilihanJawabanIndikator
    extra = 5  # Secara default otomatis memunculkan 5 baris kosong (pas untuk Level 1-5 PEMDI)
    min_num = 1 # Minimal harus ada 1 pilihan jawaban

@admin.register(IndikatorEvaluasi)
class IndikatorEvaluasiAdmin(admin.ModelAdmin):
    list_display = ('nomor_indikator', 'nama_indikator', 'tipe_penilaian', 'get_komponen')
    search_fields = ('nama_indikator',)
    list_filter = ('komponen__indeks', 'tipe_penilaian', 'komponen')
    
    # SUNTIKKAN FITUR INLINE KE DALAM FORM INDIKATOR
    inlines = [PilihanJawabanInline]

    def get_komponen(self, obj):
        return obj.komponen.nama_komponen
    get_komponen.short_description = 'Aspek'