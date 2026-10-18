# 3 Jenis Sabar — Video 30 Saat

Video pendek menegak (1080×1920, 30 saat) tentang tiga jenis sabar berdasarkan Surah Al-'Asr. Sesuai untuk Reels, TikTok dan Shorts.

▶️ **Video:** [`video/3-jenis-sabar-30s.mp4`](video/3-jenis-sabar-30s.mp4)

## Isi

1. **Hook:** Mengapa Allah menekankan *sabar* dalam Surah Al-'Asr?
2. **3 Jenis Sabar**
   - 01 · Sabar dalam **ketaatan**: istiqamah beribadah walaupun terasa berat
   - 02 · Sabar menjauhi **maksiat**: menahan diri daripada perkara yang dilarang Allah
   - 03 · Sabar menghadapi **ujian**: tetap reda dan tidak berputus asa
3. **Ingatlah:** Al-'Asr ayat 3, saling berpesan dengan kesabaran
4. **Penutup:** Sabar adalah kunci kejayaan dunia & akhirat

## Struktur

```
audio/narasi.wav          narasi asal (40.6 s)
video/3-jenis-sabar-30s.mp4  hasil akhir
scripts/transcribe.py     transkrip audio + cap masa perkataan (faster-whisper)
scripts/transcript.json   hasil transkrip
scripts/render.py         jana video: animasi, kapsyen karaoke, highlight istilah, peralihan
```

## Jana semula video

Perlu Python 3.9+ dan macOS (guna fon Avenir Next).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/transcribe.py audio/narasi.wav scripts/transcript.json
.venv/bin/python scripts/render.py audio/narasi.wav scripts/transcript.json video/3-jenis-sabar-30s.mp4
```

Untuk muat dalam 30 saat, `render.py` memendekkan jeda antara ayat dan melajukan suara (~1.25×) tanpa mengubah nada.
