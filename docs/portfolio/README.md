# Paket dokumentasi portfolio — Karsa (dulu DecisionFlow AI)

Isi folder ini siap dipindahkan ke situs portfolio (`sky-portfolio`). Belum ada file di situs portfolio yang diubah.

| Isi | Keterangan |
|---|---|
| `CASE_STUDY.md` | Studi kasus lengkap dalam bahasa Inggris (situs ber-`lang="en"`) |
| `case-karsa.html` | Draf halaman studi kasus mengikuti `case-template.html` |
| `projects-entry.js` | Entri yang perlu ditambahkan ke `projects.js` |
| `webp/` | 16 gambar desktop 1600×1000 + 2 gambar ponsel 780×1688 (format sesuai template) |
| `screenshots/` | PNG asli hasil tangkapan otomatis |

## Cara memasang nanti
1. Salin `webp/*.webp` ke `sky-portfolio/assets/projects/`.
2. Salin `case-karsa.html` ke root `sky-portfolio/`.
3. Tambahkan isi `projects-entry.js` ke array di `projects.js` (posisi menentukan urutan dan tautan "next").
4. Tambahkan kartu proyek di `index.html` dengan `data-project="decisionflow"` seperti kartu proyek lain.
5. Hapus `<meta name="robots" content="noindex, nofollow">` di halaman bila ingin diindeks.

## Mengambil ulang screenshot
Screenshot diambil otomatis dari database terpisah yang baru di-seed (demo database tidak tersentuh):

```bash
cd frontend && pnpm playwright test -c playwright.screens.config.ts
```

Lalu konversi ke WebP (nama file sudah sesuai halaman): `uv run --with pillow python scripts/screens_to_webp.py` dari root proyek. Ukuran tetap
1600×1000 / 780×1688.

## Catatan
Decision Hub (sudah ada di portfolio) dan Karsa sama-sama bertema deal desk B2B. Karsa
melanjutkan ke eksekusi terkontrol, evaluasi AI, dan pengukuran dampak. Pertimbangkan apakah keduanya ditampilkan,
atau salah satunya dijadikan tautan dari yang lain.
