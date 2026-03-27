# Third-Party Code Notice

This directory contains code from the following third-party projects:

## Fun-ASR Model Code

**Files:**
- `model.py`
- `ctc.py`
- `tools/__init__.py`
- `tools/utils.py`

**Source:** [FunAudioLLM/Fun-ASR](https://github.com/FunAudioLLM/Fun-ASR)
**License:** Apache License 2.0
**Copyright:** Copyright [2024] [FunAudioLLM]

**Modifications:** None - these are original files from the Fun-ASR project, required for loading the `FunAudioLLM/Fun-ASR-Nano-2512` model.

**License Text:** See [Fun-ASR LICENSE](https://github.com/FunAudioLLM/Fun-ASR/blob/main/LICENSE)

---

## Test Scripts

**Files:**
- `demo_reconstruct_segments.py`
- `demo_timestamp.py`
- `test_timestamps_field.py`

**Based on:** Fun-ASR official examples (Apache 2.0)
**Modifications:**
- Added bug validation logic for FunASR VAD timestamp issues
- Added segment reconstruction from VAD + timestamps
- Added detailed output and statistics
- Modified to test bug fixes in funasr 1.3.1

**VideoSieve Project License** applies to the modifications.

---

## Apache License 2.0 Requirements

In compliance with Apache License 2.0 Section 4:

1. **License Retention:** The original Apache 2.0 license is retained (see Fun-ASR LICENSE)
2. **Modification Notice:** Modified files are noted above
3. **Attribution:** Original copyright and attribution notices are preserved
4. **Patent Grant:** Apache 2.0 patent grant applies to original code

For the full Apache 2.0 license text, see:
- https://www.apache.org/licenses/LICENSE-2.0
- Fun-ASR repository: https://github.com/FunAudioLLM/Fun-ASR/blob/main/LICENSE
