"""Test if the bug-fixed timestamps field contains complete data."""

import torch
import json


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
    print("TEST: Load ASR with VAD and check timestamps field")
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

    result = asr_res[0]

    print("\n" + "="*80)
    print("COMPARING FIELDS")
    print("="*80)

    # Get both timestamp fields
    timestamps = result.get('timestamps', [])
    ctc_timestamps = result.get('ctc_timestamps', [])
    text = result['text']

    print(f"\n📊 Field completeness:")
    print(f"  text: {len(text)} chars")
    print(f"  timestamps: {len(timestamps)} tokens ({len(timestamps)/len(text)*100:.1f}% coverage)")
    print(f"  ctc_timestamps: {len(ctc_timestamps)} tokens ({len(ctc_timestamps)/len(text)*100:.1f}% coverage)")

    if timestamps:
        print(f"\n📊 timestamps field (after bug fix):")
        print(f"  First 3 tokens:")
        for i, t in enumerate(timestamps[:3]):
            print(f"    [{i}] {t}")
        print(f"  Last 3 tokens:")
        for i, t in enumerate(timestamps[-3:], start=len(timestamps)-3):
            print(f"    [{i}] {t}")

        # Check time range
        first_time = timestamps[0]['start_time']
        last_time = timestamps[-1]['end_time']
        print(f"\n  Time range: {first_time:.2f}s - {last_time:.2f}s")
        print(f"  Duration: {last_time - first_time:.2f}s")

        # Check if times are reasonable
        if last_time > 1000:  # More than 1000 seconds = likely still buggy
            print(f"  ⚠️  WARNING: End time {last_time:.2f}s seems too large!")
            print(f"  ⚠️  Bug fix may not be working correctly")
        elif last_time < 100:  # Less than 100s = likely incomplete
            print(f"  ⚠️  WARNING: End time {last_time:.2f}s seems too small for a 238s audio!")
            print(f"  ⚠️  Data may be incomplete")
        else:
            print(f"  ✅ Time range looks reasonable")

    if ctc_timestamps:
        print(f"\n📊 ctc_timestamps field:")
        print(f"  Time range: {ctc_timestamps[0]['start_time']:.2f}s - {ctc_timestamps[-1]['end_time']:.2f}s")
        print(f"  Duration: {ctc_timestamps[-1]['end_time'] - ctc_timestamps[0]['start_time']:.2f}s")

    # Save for inspection
    output = {
        "text_length": len(text),
        "timestamps_count": len(timestamps),
        "ctc_timestamps_count": len(ctc_timestamps),
        "timestamps_sample": {
            "first_3": timestamps[:3] if timestamps else [],
            "last_3": timestamps[-3:] if timestamps else []
        },
        "ctc_timestamps_sample": {
            "first_3": ctc_timestamps[:3] if ctc_timestamps else [],
            "last_3": ctc_timestamps[-3:] if ctc_timestamps else []
        }
    }

    with open("timestamps_comparison.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Saved comparison to timestamps_comparison.json")

    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)

    if timestamps and len(timestamps) > len(ctc_timestamps):
        print("\n✅ Use 'timestamps' field (more complete)")
        print(f"   - {len(timestamps)} tokens vs {len(ctc_timestamps)} tokens")
        print(f"   - {len(timestamps) - len(ctc_timestamps)} more tokens!")
    else:
        print("\n⚠️  Need further investigation")


if __name__ == "__main__":
    main()
