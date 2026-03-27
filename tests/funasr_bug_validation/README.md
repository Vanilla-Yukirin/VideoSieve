# FunASR Bug Validation Tests

这个目录包含用于验证和测试 FunASR VAD 长音频处理 bug 修复的脚本。

## Bug 背景

FunASR 1.3.0 和 1.3.1 在使用 VAD 处理长音频时存在两个 bug：
1. **KeyError: 0** - timestamp 类型假设错误
2. **单位转换错误** - VAD offset（毫秒）直接加到 timestamp（秒）

详见：[docs/FUNASR_VAD_FIX.md](../../docs/FUNASR_VAD_FIX.md)

## 前置要求

1. **必须先应用 bug 修复**到 `.venv/Lib/site-packages/funasr/auto/auto_model.py`（见文档）
2. **GPU 推荐**（CPU 模式下长音频会非常慢）
3. **测试音频**：需要准备一个长音频文件（建议 >2 分钟）

## 测试脚本

### 1. `test_timestamps_field.py` - 验证 bug 修复

验证 `timestamps` 字段在 bug 修复后是否正确：

```bash
cd tests/funasr_bug_validation
python test_timestamps_field.py
```

**预期结果：**
- ✅ `timestamps` 时间范围合理（不是 217679s 这样的异常值）
- ✅ 覆盖率 >90%
- ✅ 比 `ctc_timestamps` 更完整

### 2. `demo_timestamp.py` - 调试 timestamp 结构

详细检查 ASR 返回的各种 timestamp 字段：

```bash
python demo_timestamp.py
```

**输出文件：**
- `timestamp_debug.json` - 完整的 ASR 结果
- `vad_debug.json` - VAD 检测结果

### 3. `demo_reconstruct_segments.py` - 重建 sentence_info

从 VAD segments + timestamps 重建时间对齐的句子段落：

```bash
python demo_reconstruct_segments.py
```

**输出文件：**
- `reconstructed_segments.json` - 完整的重建结果
- `reconstructed_segments.jsonl` - VideoSieve 兼容格式

**预期结果：**
- ✅ 重建 ~22 个 segments（取决于音频内容）
- ✅ 覆盖率 >95%
- ✅ 文本完整度 >98%

## 文件说明

### 测试脚本（基于 Fun-ASR 示例修改）

- `demo_reconstruct_segments.py` - 重建 sentence_info 的完整示例
- `demo_timestamp.py` - 调试和检查 timestamp 字段结构
- `test_timestamps_field.py` - 验证 bug 修复后的正确性

### 依赖文件（来自 Fun-ASR，Apache 2.0）

- `model.py` - FunASR-Nano 模型定义（**必需**）
- `ctc.py` - CTC 解码器（**必需**）
- `tools/utils.py` - 音频处理工具（**必需**）
- `tools/__init__.py` - Python 包初始化（**必需**）

**注意：** `FunAudioLLM/Fun-ASR-Nano-2512` 是自定义模型，需要这些文件才能加载。

详见 [NOTICE.md](./NOTICE.md) 了解许可证和归属信息。

## 修改说明

基于 [FunAudioLLM/Fun-ASR](https://github.com/FunAudioLLM/Fun-ASR) 官方示例的修改：

1. **添加 bug 验证逻辑**：检查 timestamps 字段的正确性
2. **添加 segment 重建**：从 VAD + timestamps 重建 sentence_info
3. **添加详细输出**：统计信息、覆盖率分析等

## 注意事项

1. **音频路径**：脚本中硬编码了测试音频路径，使用前需要修改：
   ```python
   wav_path = r"C:\Users\Vanilla\test_audio.mp3"  # 修改为你的音频路径
   ```

2. **设备选择**：脚本会自动检测 CUDA/MPS/CPU，优先使用 GPU

3. **bug 修复状态**：这些测试**必须在应用 bug 修复后**才能正常工作

## 相关文档

- [docs/FUNASR_VAD_FIX.md](../../docs/FUNASR_VAD_FIX.md) - 完整的 bug 修复文档
- [Fun-ASR GitHub](https://github.com/FunAudioLLM/Fun-ASR) - 官方仓库
- [Fun-ASR Issue #72](https://github.com/FunAudioLLM/Fun-ASR/issues/72) - Bug 报告
- [ModelScope PR #2814](https://github.com/modelscope/FunASR/pull/2814) - 官方修复 PR

## License

这些测试脚本基于 Fun-ASR 官方示例（Apache 2.0）修改而来。
VideoSieve 项目的 LICENSE 适用于修改部分。
