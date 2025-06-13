# Clipper Academy API Documentation

## Overview
This document provides a comprehensive reference for the Clipper Academy FastAPI backend, including all endpoints, request/response models, and the asynchronous task system. Use this guide to integrate with the API, understand its capabilities, and troubleshoot common issues.

## Scope
**Covers:**
- All public API endpoints under `/api/v1`
- Request and response models
- Task system for asynchronous processing
- Error handling patterns
- Practical usage examples

**Does NOT cover:**
- Internal service implementation details
- Frontend integration specifics
- Authentication/authorization (not currently required)

For architecture or deployment details, see related documentation in the `docs/` or `.cursor/rules/` directories.

---

## Table of Contents
- [Authentication](#authentication)
- [Endpoints](#endpoints)
  - [Clips](#clips)
  - [Tasks](#tasks)
  - [Analysis](#analysis)
  - [Health](#health)
  - [Root & Ping](#root--ping)
- [Task System](#task-system)
- [Error Handling](#error-handling)
- [Models](#models)
- [Examples](#examples)
- [Checklist/Quick Reference](#checklistquick-reference)
- [Related Documentation](#related-documentation)
- [Never Do / Always Do](#never-do--always-do)

---

## Authentication
- **No authentication required** for any endpoints by default.
- If authentication is added, update this section accordingly.

---

## Endpoints

### Clips

#### POST `/clips/upload`
Upload a video file to create clips asynchronously. Returns a task ID.

**Request:**
- `multipart/form-data`
  - `file`: Video file (**required**)
  - `use_zapcap`: boolean (optional, default: false)
  - `zapcap_template_id`: string (optional)
  - `zapcap_language`: string (optional, default: "en")
  - `aspect_ratio`: string (optional, default: "9:16")
  - `max_clips`: integer (optional, default: 5)

**Response:**
- `200 OK` — `TaskResponse` (see [Models](#models))

---

#### POST `/clips/url`
Start processing a video from a social media URL asynchronously.

**Request:**
- `application/json`
  - `url`: string (**required**)
  - `use_zapcap`: boolean (optional)
  - `zapcap_template_id`: string (optional)
  - `zapcap_language`: string (optional)
  - `aspect_ratio`: string (optional)
  - `max_clips`: integer (optional)

**Response:**
- `200 OK` — `TaskResponse`

---

#### POST `/clips/file`
Start processing a video from a local file path asynchronously.

**Request:**
- `application/json`
  - `file_path`: string (**required**)
  - `use_zapcap`: boolean (optional)
  - `zapcap_template_id`: string (optional)
  - `zapcap_language`: string (optional)
  - `aspect_ratio`: string (optional)
  - `max_clips`: integer (optional)

**Response:**
- `200 OK` — `TaskResponse`

---

### Tasks

#### GET `/tasks/{task_id}`
Get the status and result of a specific task.

**Response:**
- `200 OK` — `TaskResponse`
- `404 Not Found` — If the task does not exist

---

#### GET `/tasks/`
List all tasks, optionally filtered by type.

**Query Parameters:**
- `task_type`: string (optional)

**Response:**
- `200 OK` — `TaskListResponse`

---

### Analysis

#### POST `/analysis/content`
Analyze social media content from a URL.

**Request:**
- `application/json`
  - `url`: string (**required**)
  - `language`: string (optional)
  - `extract_keyframes`: boolean (optional)
  - `max_keyframes`: integer (optional)

**Response:**
- `200 OK` — `AnalysisResponse`

---

#### POST `/analysis/transcribe`
Transcribe audio from a video or audio file.

**Request:**
- `application/json`
  - `file_path`: string (**required**)
  - `return_timestamps`: boolean (optional)

**Response:**
- `200 OK` — `TranscriptionResponse`

---

#### POST `/analysis/upload-transcribe`
Upload a file and transcribe its audio.

**Request:**
- `multipart/form-data`
  - `file`: Audio or video file (**required**)
  - `return_timestamps`: boolean (optional)

**Response:**
- `200 OK` — `TranscriptionResponse`

---

#### POST `/analysis/zapcap`
Add captions to a video using the ZapCap service.

**Request:**
- `multipart/form-data`
  - `file`: Video file (**required**)
  - `template_id`: string (**required**)
  - `language`: string (optional)
  - `auto_approve`: boolean (optional)

**Response:**
- `200 OK` — `ZapCapResponse`

---

#### GET `/analysis/formats`
Get supported file formats for analysis operations.

**Response:**
- `200 OK` — JSON object with supported formats

---

### Health

#### GET `/health/status`
Check API health.

**Response:**
- `200 OK` — `{ "status": "ok" }`

---

### Root & Ping

#### GET `/`
Root endpoint with service information.

**Response:**
- `200 OK` — Service metadata

#### GET `/ping`
Simple ping endpoint.

**Response:**
- `200 OK` — `{ "message": "pong", "timestamp": "<iso8601>" }`

---

## Task System
- All clip-processing endpoints return a `TaskResponse` with a unique `task_id`.
- Use `/tasks/{task_id}` to poll for status and results.
- Task statuses: `pending`, `processing`, `completed`, `failed`.
- When `status` is `completed`, the `result` field contains the output (e.g., clips info).

---

## Error Handling
- All errors return a JSON object with:
  - `error`: string
  - `error_type`: string
  - `detail`: string
  - `timestamp`: string

---

## Models

### TaskResponse
```json
{
  "id": "string",
  "type": "string",
  "status": "pending|processing|completed|failed",
  "created_at": "datetime",
  "updated_at": "datetime",
  "metadata": { "key": "value" },
  "result": { "key": "value" },
  "error": "string|null"
}
```

### TaskListResponse
```json
{
  "tasks": {
    "task_id": { /* TaskResponse */ }
  },
  "total": 1
}
```

### TaskStatusResponse
```json
{
  "status": "pending|processing|completed|failed",
  "progress": 0.5,
  "message": "string",
  "result": { "key": "value" },
  "error": "string|null"
}
```

*Other models (ClipResponse, AnalysisResponse, etc.) are defined in the OpenAPI schema at `/docs`.*

---

## Examples

### Upload and Poll for Clips

1. **Upload a video:**
```bash
   curl -F "file=@video.mp4" http://localhost:8000/api/v1/clips/upload
   ```
   Response:
```json
   { "id": "1234...", "status": "pending", ... }
   ```

2. **Poll for status:**
   ```bash
   curl http://localhost:8000/api/v1/tasks/1234...
   ```
   Response (when done):
```json
   { "id": "1234...", "status": "completed", "result": { ... } }
```

---

## Checklist/Quick Reference
- [x] All endpoints documented
- [x] Request/response models included
- [x] Task system explained
- [x] Error handling described
- [x] Practical examples provided
- [x] OpenAPI docs available at `/docs`

---

## Related Documentation
- [Endpoint Creation Rules](../.cursor/rules/endpoint_creation.mdc)
- [API Versioning Standards](../.cursor/rules/api_versioning_standards.mdc)
- [Testing Integration Setup](../.cursor/rules/testing_integration_setup.mdc)
- [Troubleshooting Common Errors](../.cursor/rules/troubleshooting_common_errors.mdc)

---

## Never Do / Always Do
**Never:**
- Never expose sensitive information in requests or responses
- Never skip polling the task endpoint for async operations
- Never use undocumented endpoints in production

**Always:**
- Always check the `status` field in task responses
- Always use the documented request/response formats
- Always refer to `/docs` for the latest OpenAPI schema
- Always update this documentation when endpoints change 