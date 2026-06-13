from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        # 🚨 PENTING: Ganti '0004_sebelumnya' dengan nama file migrasi terakhir 
        # yang ada di folder migrations Anda sebelum file ini dibuat.
        ('evaluasi', '0001_initial'), 
    ]

    operations = [
        migrations.CreateModel(
            name='TransaksiEvaluasi',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False, verbose_name='ID')),
                ('link_bukti_dukung', models.URLField(blank=True, max_length=500, null=True, verbose_name='Link Bukti Dukung (Drive/Cloud)')),
                ('catatan_opd', models.TextField(blank=True, null=True, verbose_name='Penjelasan/Catatan dari OPD')),
                ('catatan_supervisor', models.TextField(blank=True, null=True, verbose_name='Catatan/Rekomendasi Supervisor')),
                ('status', models.CharField(choices=[('DRAF', 'Draf (Belum Dikirim)'), ('SUBMITTED', 'Diajukan ke Supervisor'), ('VERIFIED', 'Selesai Diverifikasi')], default='DRAF', max_length=20, verbose_name='Status Dokumen')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('indeks_aktif', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transaksi_indeks_list', to='evaluasi.jenisindeks', verbose_name='Periode Evaluasi')),
                ('indikator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transaksi_list', to='evaluasi.indikatorevaluasi', verbose_name='Indikator')),
                ('opd', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hasil_evaluasi_opd', to='evaluasi.opd', verbose_name='Instansi / OPD Pengisi')),
                ('pilihan_mandiri', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pilihan_opd', to='evaluasi.pilihanjawabanindikator', verbose_name='Jawaban Mandiri')),
                ('pilihan_verifikasi', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pilihan_verifikator', to='evaluasi.pilihanjawabanindikator', verbose_name='Jawaban Hasil Verifikasi')),
                ('user_updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='modifier_transaksi', to='auth.user', verbose_name='Operator Pengubah Terakhir')),
            ],
            options={
                'verbose_name_plural': 'Transaksi Evaluasi Mandiri',
                'unique_together': {('opd', 'indeks_aktif', 'indikator')},
            },
        ),
    ]