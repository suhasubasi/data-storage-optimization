"""Local speaker diarization with cached Sherpa-ONNX models.

Labels are recording-local voice clusters, never personal identities. No audio
leaves this machine. Model files download once from the upstream release.
"""
from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

_RELEASE = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/'
_SEGMENT = 'sherpa-onnx-pyannote-segmentation-3-0'
_EMBED = '3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx'


def enabled(thresholds):
    override = os.environ.get('DSO_DIARIZATION')
    return override.lower() not in ('0', 'false', 'off') if override is not None else thresholds.get('video', {}).get('speaker_diarization', True)


def ensure_models():
    root = Path(os.environ.get('DSO_DIARIZATION_MODEL_DIR', Path(__file__).resolve().parents[1] / 'models' / 'diarization'))
    root.mkdir(parents=True, exist_ok=True)
    segmentation, embedding = root / 'segmentation.onnx', root / _EMBED
    # Temporary files on the same volume + replace keep concurrent first runs
    # and interrupted downloads from exposing incomplete model files.
    with tempfile.TemporaryDirectory(dir=root, prefix='.download-') as tmp:
        tmp = Path(tmp)
        if not segmentation.exists():
            archive = tmp / 'segmentation.tar.bz2'
            urllib.request.urlretrieve(_RELEASE + 'speaker-segmentation-models/' + _SEGMENT + '.tar.bz2', archive)
            with tarfile.open(archive) as source:
                member = source.extractfile(_SEGMENT + '/model.onnx')
                if member is None:
                    raise RuntimeError('Speaker segmentation model missing from archive')
                with member, (tmp / 'segmentation.onnx').open('wb') as target:
                    shutil.copyfileobj(member, target)
            os.replace(tmp / 'segmentation.onnx', segmentation)
        if not embedding.exists():
            urllib.request.urlretrieve(_RELEASE + 'speaker-recongition-models/' + _EMBED, tmp / _EMBED)
            os.replace(tmp / _EMBED, embedding)
    return segmentation, embedding


def speaker_turns(audio, thresholds, on_progress):
    import sherpa_onnx as sherpa
    segmentation, embedding = ensure_models()
    cfg = thresholds.get('video', {})
    config = sherpa.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation)),
            num_threads=2),
        embedding=sherpa.SpeakerEmbeddingExtractorConfig(model=str(embedding), num_threads=2),
        clustering=sherpa.FastClusteringConfig(num_clusters=-1, threshold=float(cfg.get('speaker_cluster_threshold', .75))),
        min_duration_on=.3, min_duration_off=.5)
    if not config.validate():
        raise RuntimeError('Invalid local speaker diarization configuration')
    diarizer = sherpa.OfflineSpeakerDiarization(config)
    def progress(done, total):
        on_progress(done / max(total, 1))
        return 0
    turns = diarizer.process(audio, callback=progress).sort_by_start_time()
    on_progress(1.0)
    return [(float(t.start), float(t.end), int(t.speaker)) for t in turns]


def assign_speakers(segments, words, turns):
    """Split at word boundaries; unknown/overlapping voices retain null labels.

    Every source word is emitted exactly once. Without word times a complete
    transcript segment is retained and labelled only when one voice dominates.
    """
    names = {}
    for start, end, voice in sorted(turns):
        names.setdefault(voice, f'Speaker {len(names) + 1}')

    def label(start, end):
        spans = {}
        for a, b, voice in turns:
            spans.setdefault(voice, []).append((max(a, start), min(b, end)))
        totals = {}
        for voice, intervals in spans.items():
            merged_end = start
            total = 0.
            for a, b in sorted(intervals):
                total += max(0., b - max(a, merged_end))
                merged_end = max(merged_end, b)
            totals[voice] = total
        ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        length = max(end - start, .001)
        if not ranked or ranked[0][1] < .6 * length:
            return None
        if len(ranked) > 1 and ranked[1][1] >= .3 * length:
            return None
        return names[ranked[0][0]]

    output, speakers = [], []
    for index, (start, end, text) in enumerate(segments):
        timed = words[index] if index < len(words) else []
        if not timed:
            output.append((start, end, text))
            speakers.append(label(start, end))
            continue
        groups = []
        for a, b, word in timed:
            voice = label(a, b)
            if groups and groups[-1][3] == voice:
                groups[-1][1] = b
                groups[-1][2] += word
            else:
                groups.append([a, b, word, voice])
        # Word timings normally omit leading/trailing pauses; retain source bounds.
        groups[0][0], groups[-1][1] = start, end
        for a, b, phrase, voice in groups:
            output.append((round(a, 3), round(b, 3), phrase.strip()))
            speakers.append(voice)
    return output, speakers
