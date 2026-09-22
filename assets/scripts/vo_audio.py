"""vo_audio.py -- concatenate VO segments with pauses at one common format.

Segments can arrive at different sample rates (edge-tts and ElevenLabs don't
agree), so a plain concat demuxer would desync. concat_with_pauses decodes
every segment (and generated silence) to ONE sample rate/channel layout via
ffmpeg's filter_complex concat filter, instead of the concat demuxer.
"""
import subprocess


def concat_with_pauses(segments, out_path, sample_rate=44100):
    inputs = []
    filter_parts = []
    concat_labels = []
    idx = 0
    for mp3_path, pause_after in segments:
        inputs += ["-i", mp3_path]
        out_label = f"a{idx}"
        filter_parts.append(
            f"[{idx}:a]aformat=sample_rates={sample_rate}:channel_layouts=mono[{out_label}]")
        concat_labels.append(f"[{out_label}]")
        idx += 1
        if pause_after and pause_after > 0:
            inputs += ["-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono:d={pause_after}"]
            sil_label = f"a{idx}"
            filter_parts.append(
                f"[{idx}:a]aformat=sample_rates={sample_rate}:channel_layouts=mono[{sil_label}]")
            concat_labels.append(f"[{sil_label}]")
            idx += 1

    n = len(concat_labels)
    concat_filter = "".join(concat_labels) + f"concat=n={n}:v=0:a=1[aout]"
    filter_complex = ";".join(filter_parts + [concat_filter])

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
           "-filter_complex", filter_complex, "-map", "[aout]",
           "-c:a", "libmp3lame", "-b:a", "192k", out_path]
    subprocess.run(cmd, check=True)
