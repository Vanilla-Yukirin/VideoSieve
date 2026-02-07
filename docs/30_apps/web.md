# App: web

## Purpose

提供项目列表、详情、控制与产物浏览界面。

## Core Views

- Projects list (project-level summary)
- Project detail (history of jobs + selected job view)
- Job detail (logs/timeline/artifacts/controls)
- Settings (provider/key/concurrency/strategy defaults)

## Interaction Model

- REST for CRUD and snapshots
- WebSocket primarily on `job_id` channel for realtime events and controls

## UI State Rules

- 页面进入时先拉 HTTP snapshot，再建立 WS 订阅。
- WS 断开/丢事件时回退到 snapshot 轮询，不以 WS 作为唯一状态来源。
