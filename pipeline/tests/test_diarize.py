from dso_pipeline.diarize import assign_speakers, enabled


def test_returning_voice_retains_label_and_splits_words():
    segments = [(0., 4., 'Hello there. Good morning. Welcome back.')]
    words = [[(0., .5, ' Hello'), (.5, 1., ' there.'), (1., 1.5, ' Good'), (1.5, 2., ' morning.'), (3., 3.5, ' Welcome'), (3.5, 4., ' back.')]]
    output, speakers = assign_speakers(segments, words, [(0, 1, 7), (1, 2, 3), (3, 4, 7)])
    assert speakers == ['Speaker 1', 'Speaker 2', 'Speaker 1']
    assert output == [(0., 1., 'Hello there.'), (1., 2., 'Good morning.'), (3., 4., 'Welcome back.')]
    assert ' '.join(text for _, _, text in output) == segments[0][2]


def test_silence_overlap_and_missing_turns_stay_unknown():
    segments = [(0, 1, 'Unknown'), (1, 2, 'Overlapping'), (3, 4, 'Known')]
    output, labels = assign_speakers(segments, [], [(1, 2, 4), (1, 2, 9), (3, 4, 4)])
    assert output == segments
    assert labels == [None, None, 'Speaker 1']


def test_segment_without_words_requires_dominant_voice():
    assert assign_speakers([(0, 4, 'Mixed')], [], [(0, 2, 0), (2, 4, 1)])[1] == [None]


def test_disabled_by_configuration_or_environment(monkeypatch):
    monkeypatch.delenv('DSO_DIARIZATION', raising=False)
    assert enabled({})
    assert not enabled({'video': {'speaker_diarization': False}})
    monkeypatch.setenv('DSO_DIARIZATION', 'off')
    assert not enabled({})


def test_pipeline_writes_speakers_and_retains_transcript_on_diarizer_failure(tmp_path, monkeypatch):
    from dso_pipeline import video
    from dso_pipeline.common import Status
    from dso_pipeline.transcribe import TranscriptResult
    monkeypatch.delenv('DSO_TRANSCRIBER', raising=False)
    monkeypatch.delenv('DSO_DIARIZATION', raising=False)
    monkeypatch.setattr(video, 'probe', lambda p: {'format': {'duration': '2'}, 'streams': [{'codec_type': 'audio'}]})
    monkeypatch.setattr(video, '_run', lambda cmd: None)
    monkeypatch.setattr(video, 'load_wav_16k_mono', lambda p: [])
    monkeypatch.setattr(video, 'transcribe', lambda *a, **kw: TranscriptResult(
        [(0, 2, 'Hello. Hi.')], 'en', 'test', words=[[(0, 1, 'Hello.'), (1, 2, ' Hi.')]]))
    monkeypatch.setattr(video.diarize, 'speaker_turns', lambda *a: [(0, 1, 5), (1, 2, 9)])
    result = video.process_video(tmp_path/'audio.mp4', tmp_path, {}, Status(tmp_path))
    assert [s['speaker'] for s in result['segments']] == ['Speaker 1', 'Speaker 2']
    assert [s['text'] for s in result['segments']] == ['Hello.', 'Hi.']
    assert all(s['frame_id'] is None for s in result['segments'])
    import json
    assert json.loads((tmp_path/'transcript.json').read_text())['segments'] == result['segments']
    def fail(*a):
        raise RuntimeError('Test model load failure')
    monkeypatch.setattr(video.diarize, 'speaker_turns', fail)
    result = video.process_video(tmp_path/'audio.mp4', tmp_path, {}, Status(tmp_path))
    assert result['segments'][0]['text'] == 'Hello. Hi.'
    assert result['segments'][0]['speaker'] is None
    assert any('speaker diarization unavailable' in w for w in result['warnings'])
