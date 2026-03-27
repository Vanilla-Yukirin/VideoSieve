"""Reconstruct sentence_info from VAD segments and word-level timestamps (after bug fix)."""

import torch
import json
from typing import List, Dict, Any


def reconstruct_segments_from_vad_and_timestamps(
    vad_segments: List[List[int]],
    timestamps: List[Dict[str, Any]],
    text: str
) -> List[Dict[str, Any]]:
    """
    Reconstruct sentence_info from VAD segments and word-level timestamps.

    Args:
        vad_segments: List of [start_ms, end_ms] from VAD
        timestamps: List of {token, start_time, end_time, score} from ASR
        text: Full transcription text

    Returns:
        List of segments with {segment_id, start, end, text, conf}
    """
    segments = []

    for idx, (start_ms, end_ms) in enumerate(vad_segments, start=1):
        # Convert milliseconds to seconds
        start_sec = start_ms / 1000.0
        end_sec = end_ms / 1000.0

        # Find all tokens in this time range
        tokens_in_segment = [
            t for t in timestamps
            if start_sec <= t['start_time'] < end_sec
        ]

        if not tokens_in_segment:
            # Empty segment (silence), skip or mark as empty
            continue

        # Build segment text
        segment_text = "".join([t['token'] for t in tokens_in_segment])

        # Calculate average confidence
        avg_conf = sum(t['score'] for t in tokens_in_segment) / len(tokens_in_segment)

        # Get actual start/end from tokens (more precise than VAD boundaries)
        actual_start = tokens_in_segment[0]['start_time']
        actual_end = tokens_in_segment[-1]['end_time']

        segments.append({
            "segment_id": f"seg_{idx:05d}",
            "start": actual_start,
            "end": actual_end,
            "text": segment_text,
            "conf": round(avg_conf, 3),
            "vad_start": start_sec,  # Original VAD boundary
            "vad_end": end_sec,
        })

    return segments


def main():
    model_dir = "FunAudioLLM/Fun-ASR-Nano-2512"
    device = (
        "cuda:0"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )

    from funasr import AutoModel

    print(f"🔧 Using device: {device}\n")

    wav_path = r"C:\Users\Vanilla\test_audio.mp3"

    print("="*80)
    print("STEP 1: Load ASR model with VAD")
    print("="*80)

    model_with_vad = AutoModel(
        model=model_dir,
        trust_remote_code=True,
        remote_code="./model.py",
        device=device,
        hub="ms",
        vad_model="fsmn-vad",
        vad_kwargs={"max_single_segment_time": 30000}
    )

    print("\n🔧 Running ASR with VAD...")
    asr_res = model_with_vad.generate(
        input=[wav_path],
        cache={},
        batch_size=1,
        language="中文",
        itn=True,
    )

    print("="*80)
    print("STEP 2: Load standalone VAD model")
    print("="*80)

    vad_model = AutoModel(
        model="fsmn-vad",
        device=device,
        hub="ms"
    )

    print("\n🔧 Running VAD detection...")
    vad_res = vad_model.generate(
        input=[wav_path],
        cache={},
        batch_size=1,
    )

    print("="*80)
    print("STEP 3: Extract data")
    print("="*80)

    # Extract VAD segments
    vad_segments = vad_res[0]['value']
    print(f"\n✅ VAD segments: {len(vad_segments)} segments")
    print(f"  First: {vad_segments[0]} ({vad_segments[0][0]/1000:.2f}s - {vad_segments[0][1]/1000:.2f}s)")
    print(f"  Last:  {vad_segments[-1]} ({vad_segments[-1][0]/1000:.2f}s - {vad_segments[-1][1]/1000:.2f}s)")

    # Extract timestamps (using 'timestamps' instead of 'ctc_timestamps' for completeness)
    # ctc_timestamps only has ~1656 tokens covering 9s
    # timestamps has ~1840 tokens covering 227s (after bug fix)
    timestamps = asr_res[0]['timestamps']
    print(f"\n✅ Timestamps: {len(timestamps)} tokens")
    print(f"  First: {timestamps[0]}")
    print(f"  Last:  {timestamps[-1]}")

    # Extract text
    text = asr_res[0]['text']
    print(f"\n✅ Text length: {len(text)} characters")

    print("\n" + "="*80)
    print("STEP 4: Reconstruct segments")
    print("="*80)

    segments = reconstruct_segments_from_vad_and_timestamps(
        vad_segments=vad_segments,
        timestamps=timestamps,
        text=text
    )

    print(f"\n✅ Reconstructed {len(segments)} segments\n")

    # Display first 5 segments
    print("📊 First 5 segments:")
    for seg in segments[:5]:
        print(f"  [{seg['segment_id']}] {seg['start']:.2f}s - {seg['end']:.2f}s")
        print(f"    Text ({len(seg['text'])} chars): {seg['text'][:50]}...")
        print(f"    Confidence: {seg['conf']:.3f}")
        print()

    # Display last 5 segments
    print("📊 Last 5 segments:")
    for seg in segments[-5:]:
        print(f"  [{seg['segment_id']}] {seg['start']:.2f}s - {seg['end']:.2f}s")
        print(f"    Text ({len(seg['text'])} chars): {seg['text'][:50]}...")
        print(f"    Confidence: {seg['conf']:.3f}")
        print()

    # Statistics
    total_duration = segments[-1]['end'] - segments[0]['start']
    total_chars = sum(len(seg['text']) for seg in segments)
    avg_chars_per_seg = total_chars / len(segments)

    print("="*80)
    print("STATISTICS")
    print("="*80)
    print(f"Total segments: {len(segments)}")
    print(f"Total duration: {total_duration:.2f}s")
    print(f"Total characters: {total_chars}")
    print(f"Average chars per segment: {avg_chars_per_seg:.1f}")
    print(f"Average segment duration: {total_duration/len(segments):.2f}s")

    # Check coverage
    vad_total_duration = sum((end - start) / 1000.0 for start, end in vad_segments)
    print(f"\nVAD total duration: {vad_total_duration:.2f}s")
    print(f"Reconstructed duration: {total_duration:.2f}s")
    print(f"Coverage: {total_duration/vad_total_duration*100:.1f}%")

    # Save to JSON
    output = {
        "schema_version": "1.0",
        "audio_path": wav_path,
        "total_duration": total_duration,
        "num_segments": len(segments),
        "segments": segments
    }

    with open("reconstructed_segments.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Saved to reconstructed_segments.json")

    # Also save in JSONL format (VideoSieve compatible)
    with open("reconstructed_segments.jsonl", "w", encoding="utf-8") as f:
        for seg in segments:
            record = {
                "schema_version": "1.0",
                "segment_id": seg["segment_id"],
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"],
                "lang": "zh",  # Chinese
                "conf": seg["conf"]
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"💾 Saved to reconstructed_segments.jsonl (VideoSieve format)")

    print("\n" + "="*80)
    print("SUCCESS")
    print("="*80)
    print("✅ Successfully reconstructed sentence_info from VAD + timestamps!")
    print("✅ Time-aligned segments ready for VideoSieve integration")
    print(f"✅ Used bug-fixed 'timestamps' field ({len(timestamps)} tokens)")
    print(f"   (ctc_timestamps only had {len(asr_res[0].get('ctc_timestamps', []))} tokens covering 9s)")


if __name__ == "__main__":
    main()
