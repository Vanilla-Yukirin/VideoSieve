# FunASR VAD 长音频处理修复记录

## 问题描述

**影响版本：** funasr 1.3.0, 1.3.1

**症状：** 使用 VAD (Voice Activity Detection) 处理长音频时，出现 `KeyError: 0` 错误，导致转录中断。

```
File "funasr/auto/auto_model.py", line 558, in inference_with_vad
    t[0] += vadsegments[j][0]
    ~^^^
KeyError: 0
```

**根本原因：**

FunASR 的 `inference_with_vad` 方法在处理 timestamp 时，假设所有 timestamp 都是 list/tuple 格式，直接使用索引访问 `t[0]` 和 `t[1]`。但实际上某些情况下 timestamp 可能是 dict 格式（包含 `start_time` 和 `end_time` 键），导致 `KeyError: 0`。

**相关 Issue：**
- GitHub Issue: https://github.com/FunAudioLLM/Fun-ASR/issues/72
- GitHub PR: https://github.com/modelscope/FunASR/pull/2814

---

## 修复方案

### 修复文件

```
.venv/Lib/site-packages/funasr/auto/auto_model.py
```

### 修复代码（约第 554-560 行）

**修复前（有 bug）：**

```python
if k.startswith("timestamp"):
    if k not in result:
        result[k] = []
    for t in restored_data[j][k]:
        t[0] += vadsegments[j][0]  # ❌ 假设 t 是 list/tuple
        t[1] += vadsegments[j][0]
    result[k].extend(restored_data[j][k])
```

**修复后（第一版 - 只修复 KeyError，但仍有单位bug）：**

```python
if k.startswith("timestamp"):
    if k not in result:
        result[k] = []
    for t in restored_data[j][k]:
        if isinstance(t, (list, tuple)):
            t[0] += vadsegments[j][0]  # ⚠️ 仍有单位问题
            t[1] += vadsegments[j][0]
        elif isinstance(t, dict):
            t["start_time"] = t.get("start_time", 0) + vadsegments[j][0]
            t["end_time"] = t.get("end_time", 0) + vadsegments[j][0]
    result[k].extend(restored_data[j][k])
```

**修复后（第二版 - 完整修复，包含单位转换）：**

```python
if k.startswith("timestamp"):
    if k not in result:
        result[k] = []
    for t in restored_data[j][k]:
        if isinstance(t, (list, tuple)):
            t[0] += vadsegments[j][0] / 1000.0  # ✅ 毫秒转秒
            t[1] += vadsegments[j][0] / 1000.0
        elif isinstance(t, dict):
            t["start_time"] = t.get("start_time", 0) + vadsegments[j][0] / 1000.0
            t["end_time"] = t.get("end_time", 0) + vadsegments[j][0] / 1000.0
    result[k].extend(restored_data[j][k])
```

### 关键改动

**第一版修复（解决 KeyError）：**
1. **添加类型检查：** 使用 `isinstance()` 判断 `t` 的类型
2. **list/tuple 情况：** 保留原有的索引访问方式
3. **dict 情况：** 使用键名访问 `start_time` 和 `end_time`

**第二版修复（解决单位转换bug）：**
4. **单位转换：** `vadsegments[j][0]` 是**毫秒**，timestamp 是**秒**
5. **修复方法：** 除以 1000.0 将毫秒转换为秒
6. **影响：** 修复后 `timestamps` 字段时间从异常的 217679.54s 变为正确的 227.21s

**Bug 详细分析：**
- VAD segments: `[290, 13650]` 单位是**毫秒**（0.29s - 13.65s）
- 原代码：`0.3 + 290 = 290.3s` ❌（错误！将毫秒值直接加到秒值）
- 修复后：`0.3 + 290/1000 = 0.59s` ✅（正确）

---

## 测试结果

### 测试环境
- **funasr 版本：** 1.3.1
- **测试音频：** 238.93 秒（约 4 分钟）
- **设备：** CUDA GPU

### 修复前
```
[FAIL] Failed: 0
KeyError: 0
```

### 修复后（第一版 - KeyError 修复）
```
[OK] Success! Took 43.98s
Text length: 1864 characters
完整转录文本（无重复，无丢失）
⚠️ 但 timestamps 字段时间异常：0.59s - 217679.54s
```

### 修复后（第二版 - 完整修复）
```
[OK] Success! Took 41.96s
Text length: 1864 characters
timestamps 字段：1840 tokens, 0.59s - 227.21s ✅
覆盖率：226.62s / 238.93s = 94.8% ✅
重建 segments：22 个，覆盖率 106.6% ✅
```

### 性能对比

| 方法 | 状态 | 时间 | 字符数 | Segments | 备注 |
|------|------|------|--------|----------|------|
| 不用 VAD | ❌ 失败 | 3s | 41 | N/A | 丢失 97.8% 内容 |
| 手动 30s 切割 | ✅ 成功 | ~50s | 1838 | 8 | 可靠但慢 |
| README + 第一版修复 | ⚠️ 部分 | 44s | 1864 | 0 | 文本完整，timestamps 异常 |
| **README + 完整修复** | **✅ 成功** | **42s** | **1864** | **22** | **最优方案** |

### 字段对比（修复后）

| 字段 | Token数 | 时间范围 | 完整度 | 可用性 |
|------|---------|----------|--------|--------|
| `ctc_timestamps` | 1656 | 0.3s - 9.42s | 88.8% | ❌ 不完整 |
| `timestamps` | **1840** | **0.59s - 227.21s** | **98.7%** | **✅ 推荐** |

---

## 使用方法

### 方法一：手动应用补丁（临时）

```bash
# 修改 .venv/Lib/site-packages/funasr/auto/auto_model.py
# 应用上述修复代码
```

**缺点：** `uv sync` 会覆盖修改

### 方法二：等待官方修复（推荐）

关注 PR #2814 的合并状态，升级到包含修复的版本。

---

## VideoSieve 集成建议

使用 README 方法（初始化时启用 VAD）：

```python
from funasr import AutoModel

model = AutoModel(
    model="FunAudioLLM/Fun-ASR-Nano-2512",
    trust_remote_code=True,
    remote_code="fun_asr/model.py",
    device="cuda:0",
    hub="ms",
    vad_model="fsmn-vad",  # 🔑 启用 VAD
    vad_kwargs={"max_single_segment_time": 30000}  # 🔑 最大 30 秒/段
)

res = model.generate(
    input=[audio_path],
    cache={},
    batch_size=1,
    language="中文",
    itn=True,
)
```

**优势：**
- ✅ 自动 VAD 分段
- ✅ 处理任意长度音频
- ✅ 完整转录（无重复、无丢失）
- ✅ 性能优于手动切割

### 重建 sentence_info（时间戳分段）

由于 FunASR 不返回 `sentence_info`，需要从 VAD + timestamps 重建：

```python
from funasr import AutoModel

# 1. 使用 VAD 运行 ASR
model = AutoModel(
    model="FunAudioLLM/Fun-ASR-Nano-2512",
    vad_model="fsmn-vad",
    vad_kwargs={"max_single_segment_time": 30000},
    # ... 其他参数
)

asr_res = model.generate(input=[audio_path], ...)

# 2. 单独运行 VAD 获取段落边界
vad_model = AutoModel(model="fsmn-vad", device=device, hub="ms")
vad_res = vad_model.generate(input=[audio_path], ...)
vad_segments = vad_res[0]['value']  # [[start_ms, end_ms], ...]

# 3. 使用 timestamps 字段（不是 ctc_timestamps！）
timestamps = asr_res[0]['timestamps']  # 1840 tokens, 98.7% 覆盖率

# 4. 重建 segments
def reconstruct_segments(vad_segments, timestamps):
    segments = []
    for idx, (start_ms, end_ms) in enumerate(vad_segments):
        start_sec = start_ms / 1000.0
        end_sec = end_ms / 1000.0

        # 找到该 VAD 段落内的所有 token
        tokens = [t for t in timestamps
                 if start_sec <= t['start_time'] < end_sec]

        if not tokens:
            continue

        segment = {
            "segment_id": f"seg_{idx:05d}",
            "start": tokens[0]['start_time'],
            "end": tokens[-1]['end_time'],
            "text": "".join([t['token'] for t in tokens]),
            "conf": sum(t['score'] for t in tokens) / len(tokens)
        }
        segments.append(segment)

    return segments

segments = reconstruct_segments(vad_segments, timestamps)
# 结果：22 个 segments，覆盖率 106.6%
```

**重建结果：**
- ✅ 22 个 segments（与 VAD 一致）
- ✅ 覆盖率 106.6%（226.62s / 212.49s）
- ✅ 文本完整度 98.8%（1842/1864 chars）
- ✅ 完整示例见 `Fun-ASR/demo_reconstruct_segments.py`

---

## 注意事项

1. **GPU 必需：** CPU 模式下长音频会非常慢
2. **修复状态：** 截至 2026-03-27，funasr 1.3.1 **仍需手动打补丁**
3. **两个 Bug 需要修复：**
   - Bug 1: `KeyError: 0`（添加类型检查）
   - Bug 2: 单位转换错误（除以 1000.0）
4. **使用 `timestamps` 字段：** 不要使用 `ctc_timestamps`（只有 9s 数据）
5. **sentence_info 重建：** 从 VAD segments + `timestamps` 字段重建（见 `demo_reconstruct_segments.py`）

---

## 更新日志

- **2026-03-27 上午：** 发现 `KeyError: 0` 问题并应用第一版修复
- **2026-03-27 下午：** 发现单位转换 bug（毫秒 vs 秒），应用完整修复
- **2026-03-27 下午：** 验证 `timestamps` 字段完整性（1840 tokens, 98.7%）
- **2026-03-27 下午：** 成功重建 22 个 segments，覆盖率 106.6%
- **待跟进：** 监控 PR #2814 合并到官方版本的进度
