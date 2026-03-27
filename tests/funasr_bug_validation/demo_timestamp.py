"""Test timestamp extraction from FunASR VAD results."""

import torch
import json
from pprint import pprint


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

    # Test audio
    wav_path = r"C:\Users\Vanilla\test_audio.mp3"

    print("="*80)
    print("TEST 1: README method with VAD")
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

    res = model_with_vad.generate(
        input=[wav_path],
        cache={},
        batch_size=1,
        language="中文",
        itn=True,
    )

    if res and isinstance(res[0], dict):
        result = res[0]

        print(f"\n📋 Available keys:")
        for key in result.keys():
            print(f"  - {key}")

        # Check sentence_info
        print(f"\n📊 sentence_info:")
        if "sentence_info" in result:
            sentence_info = result["sentence_info"]
            print(f"  Type: {type(sentence_info)}")
            print(f"  Length: {len(sentence_info) if sentence_info else 0}")
            if sentence_info:
                print(f"  First 3 items:")
                for i, item in enumerate(sentence_info[:3]):
                    print(f"    [{i}] {item}")
        else:
            print(f"  ❌ Not found")

        # Check timestamps (word-level)
        print(f"\n📊 timestamps:")
        if "timestamps" in result:
            timestamps = result["timestamps"]
            print(f"  Type: {type(timestamps)}")
            print(f"  Length: {len(timestamps) if timestamps else 0}")
            if timestamps and len(timestamps) > 0:
                print(f"  First 5 items:")
                for i, item in enumerate(timestamps[:5]):
                    print(f"    [{i}] {item}")
                print(f"  Last 5 items:")
                for i, item in enumerate(timestamps[-5:], start=len(timestamps)-5):
                    print(f"    [{i}] {item}")
        else:
            print(f"  ❌ Not found")

        # Check ctc_timestamps
        print(f"\n📊 ctc_timestamps:")
        if "ctc_timestamps" in result:
            ctc_ts = result["ctc_timestamps"]
            print(f"  Type: {type(ctc_ts)}")
            print(f"  Length: {len(ctc_ts) if ctc_ts else 0}")
            if ctc_ts and len(ctc_ts) > 0:
                print(f"  First 5 items:")
                for i, item in enumerate(ctc_ts[:5]):
                    print(f"    [{i}] {item}")
        else:
            print(f"  ❌ Not found")

        # Save full result to JSON for inspection
        print(f"\n💾 Saving full result to timestamp_debug.json...")
        with open("timestamp_debug.json", "w", encoding="utf-8") as f:
            # Convert to serializable format
            serializable = {}
            for k, v in result.items():
                if isinstance(v, str):
                    serializable[k] = v
                elif isinstance(v, (list, dict)):
                    serializable[k] = v
                else:
                    serializable[k] = str(v)
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        print(f"  ✅ Saved")

    print("\n" + "="*80)
    print("TEST 2: Try different VAD kwargs")
    print("="*80)

    # Try with different parameters
    print("\n🔧 Testing with return_raw_text=True...")
    model_with_vad2 = AutoModel(
        model=model_dir,
        trust_remote_code=True,
        remote_code="./model.py",
        device=device,
        hub="ms",
        vad_model="fsmn-vad",
        vad_kwargs={
            "max_single_segment_time": 30000,
        }
    )

    res2 = model_with_vad2.generate(
        input=[wav_path],
        cache={},
        batch_size=1,
        language="中文",
        itn=True,
        return_raw_text=False,  # Try to get more details
    )

    if res2 and isinstance(res2[0], dict):
        result2 = res2[0]
        print(f"\n📋 Keys with return_raw_text=False:")
        for key in result2.keys():
            print(f"  - {key}")

        if "sentence_info" in result2 and result2["sentence_info"]:
            print(f"\n✅ sentence_info found!")
            print(f"  Count: {len(result2['sentence_info'])}")
            print(f"  First item: {result2['sentence_info'][0]}")
        else:
            print(f"\n❌ Still no sentence_info")

    print("\n" + "="*80)
    print("TEST 3: Manual VAD + ASR")
    print("="*80)

    # Load VAD separately
    print("\n🔧 Loading standalone VAD model...")
    vad_model = AutoModel(
        model="fsmn-vad",
        device=device,
        hub="ms"
    )

    # Run VAD first
    print(f"🔧 Running VAD detection...")
    vad_res = vad_model.generate(
        input=[wav_path],
        cache={},
        batch_size=1,
    )

    print(f"\n📊 VAD results:")
    if vad_res and isinstance(vad_res[0], dict):
        vad_result = vad_res[0]
        print(f"  Keys: {list(vad_result.keys())}")

        if "segments" in vad_result:
            segments = vad_result["segments"]
            print(f"  Number of segments: {len(segments)}")
            print(f"  First 5 segments:")
            for i, seg in enumerate(segments[:5]):
                print(f"    [{i}] {seg}")

        # Save VAD result
        with open("vad_debug.json", "w", encoding="utf-8") as f:
            serializable = {}
            for k, v in vad_result.items():
                if isinstance(v, (str, list, dict, int, float)):
                    serializable[k] = v
                else:
                    serializable[k] = str(v)
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        print(f"  💾 Saved to vad_debug.json")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("\nCheck the following files for detailed analysis:")
    print("  - timestamp_debug.json: Full ASR result with VAD")
    print("  - vad_debug.json: Standalone VAD detection result")


if __name__ == "__main__":
    main()
