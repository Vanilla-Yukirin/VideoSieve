# VideoSieve API 文档

## 基础信息

- **Base URL**: `http://localhost:8000/api`
- **Content-Type**: `application/json`
- **SSE**: `text/event-stream`

## API 端点

### 任务管理

#### 创建任务

创建一个新的视频处理任务。

```http
POST /api/tasks/
Content-Type: application/json

{
  "video_url": "https://www.youtube.com/watch?v=..."
}
```

**响应 (201 Created)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "video_url": "https://www.youtube.com/watch?v=...",
  "status": "pending",
  "progress": 0,
  "error_message": null,
  "audio_path": null,
  "transcript": null,
  "optimized_text": null,
  "summary": null,
  "logs": [
    {
      "time": "2024-01-01T12:00:00",
      "message": "任务已创建"
    }
  ],
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:00:00"
}
```

#### 获取任务列表

获取所有任务的列表。

```http
GET /api/tasks/?skip=0&limit=100
```

**响应 (200 OK)**:
```json
{
  "tasks": [
    {
      "id": "...",
      "video_url": "...",
      "status": "completed",
      "progress": 100,
      ...
    }
  ],
  "total": 10
}
```

#### 获取单个任务

获取指定任务的详细信息。

```http
GET /api/tasks/{task_id}
```

**响应 (200 OK)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "video_url": "...",
  "status": "completed",
  "progress": 100,
  ...
}
```

**错误 (404 Not Found)**:
```json
{
  "detail": "Task {task_id} not found"
}
```

#### 删除任务

删除指定任务及其关联的音频文件。

```http
DELETE /api/tasks/{task_id}
```

**响应 (204 No Content)**

**错误 (404 Not Found)**:
```json
{
  "detail": "Task {task_id} not found"
}
```

### 任务内容

#### 获取转录文本

获取任务的原始转录文本。

```http
GET /api/tasks/{task_id}/transcript
```

**响应 (200 OK)**:
```json
{
  "transcript": "这是转录的文本内容..."
}
```

**错误 (404 Not Found)**:
```json
{
  "detail": "Transcript not yet available"
}
```

#### 获取优化文本

获取 AI 优化后的文本。

```http
GET /api/tasks/{task_id}/optimized
```

**响应 (200 OK)**:
```json
{
  "optimized_text": "这是优化后的文本内容..."
}
```

#### 获取摘要

获取任务的摘要。

```http
GET /api/tasks/{task_id}/summary
```

**响应 (200 OK)**:
```json
{
  "summary": "这是视频内容的摘要..."
}
```

### 实时更新 (SSE)

#### 订阅任务进度

通过 Server-Sent Events (SSE) 实时接收任务更新。

```http
GET /api/tasks/{task_id}/stream
Accept: text/event-stream
```

**SSE 事件格式**:
```
data: {"task_id":"...","status":"downloading","progress":30,"logs":[...],"error_message":null}

data: {"task_id":"...","status":"transcribing","progress":50,"logs":[...],"error_message":null}

data: {"task_id":"...","status":"completed","progress":100,"logs":[...],"error_message":null}
```

**心跳**:
每 30 秒发送一次心跳以保持连接：
```
: heartbeat
```

**连接关闭**:
当任务状态变为 `completed` 或 `failed` 时，连接自动关闭。

### 健康检查

#### 根端点

```http
GET /
```

**响应**:
```json
{
  "name": "VideoSieve API",
  "version": "1.0.0",
  "status": "running"
}
```

#### 健康检查

```http
GET /health
```

**响应**:
```json
{
  "status": "healthy"
}
```

## 数据模型

### Task

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 任务 UUID |
| video_url | string | 视频 URL |
| status | string | 任务状态 |
| progress | integer | 进度 (0-100) |
| error_message | string? | 错误信息 |
| audio_path | string? | 音频文件路径 |
| transcript | string? | 转录文本 |
| optimized_text | string? | 优化文本 |
| summary | string? | 摘要 |
| logs | array | 日志数组 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 任务状态

| 状态 | 说明 |
|------|------|
| pending | 等待处理 |
| downloading | 下载音频中 |
| transcribing | 转录中 |
| processing | AI 处理中 |
| completed | 已完成 |
| failed | 失败 |

### LogEntry

| 字段 | 类型 | 说明 |
|------|------|------|
| time | string | ISO 8601 时间戳 |
| message | string | 日志消息 |

## 错误处理

所有错误响应遵循 FastAPI 标准格式：

```json
{
  "detail": "错误描述"
}
```

常见状态码：
- `200 OK`: 成功
- `201 Created`: 创建成功
- `204 No Content`: 删除成功
- `404 Not Found`: 资源不存在
- `422 Unprocessable Entity`: 验证错误
- `500 Internal Server Error`: 服务器错误

## 使用示例

### JavaScript/TypeScript

```typescript
// 创建任务
const response = await fetch('http://localhost:8000/api/tasks/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ video_url: 'https://...' })
});
const task = await response.json();

// 订阅 SSE 更新
const eventSource = new EventSource(
  `http://localhost:8000/api/tasks/${task.id}/stream`
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Progress:', data.progress, '%');
  
  if (data.status === 'completed') {
    eventSource.close();
  }
};
```

### Python

```python
import requests

# 创建任务
response = requests.post(
    'http://localhost:8000/api/tasks/',
    json={'video_url': 'https://...'}
)
task = response.json()

# 获取任务详情
response = requests.get(f'http://localhost:8000/api/tasks/{task["id"]}')
task = response.json()
print(f'Status: {task["status"]}, Progress: {task["progress"]}%')
```

### cURL

```bash
# 创建任务
curl -X POST http://localhost:8000/api/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"video_url":"https://..."}'

# 获取任务列表
curl http://localhost:8000/api/tasks/

# 删除任务
curl -X DELETE http://localhost:8000/api/tasks/{task_id}

# 订阅 SSE
curl -N http://localhost:8000/api/tasks/{task_id}/stream
```

## 速率限制

当前版本无速率限制，生产环境建议配置。

## API 文档

启动服务器后，访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
