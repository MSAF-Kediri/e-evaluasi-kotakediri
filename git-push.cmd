@echo off
:: Mengubah judul jendela CMD
title Skrip Otomatisasi Git Push - Pemdi Kota Kediri

echo ====================================================
echo       OTOMATISASI GIT PUSH TO GITHUB PRIVATE
echo ====================================================
echo.

:: 1. Melakukan Git Add untuk menandai semua perubahan file
echo [1/3] Menandai semua perubahan file (git add) ...
git add .
echo Bersiap mengunggah file yang diubah.
echo.

:: 2. Meminta input catatan perubahan dari pengguna
:input_pesan
set /p pesan="[2/3] Masukkan catatan perubahan Anda (Wajib): "

:: Validasi jika pengguna langsung menekan enter tanpa mengisi pesan
if "%pesan%"=="" (
    clsc
    echo ❌ Gagal: Catatan perubahan tidak boleh kosong!
    echo.
    goto input_pesan
)

:: 3. Melakukan Git Commit dengan pesan yang diinput
echo.
echo Mengunci data versi lokal...
git commit -m "%pesan%"
echo.

:: 4. Melakukan Git Push ke GitHub
echo [3/3] Mengirim file ke GitHub (git push) ...
git push
echo.

echo ====================================================
echo  ✅ BERHASIL! Kode terbaru telah aman di GitHub.
echo ====================================================
echo.
pause