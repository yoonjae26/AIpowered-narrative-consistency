# NarrativeOS API Specification

## Base URL
```
Development: http://localhost:8000
Production: https://api.narrativeos.com
```

## Authentication
All authenticated endpoints require a Bearer token:
```
Authorization: Bearer <jwt_token>
```

## Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login and get tokens
- `POST /api/auth/refresh` - Refresh access token
- `POST /api/auth/logout` - Logout

### Projects
- `GET /api/projects` - List all projects
- `POST /api/projects` - Create new project
- `GET /api/projects/{id}` - Get project details
- `PUT /api/projects/{id}` - Update project
- `DELETE /api/projects/{id}` - Delete project

### Characters
- `GET /api/projects/{id}/characters` - List characters
- `POST /api/projects/{id}/characters` - Create character
- `GET /api/characters/{id}` - Get character details
- `PUT /api/characters/{id}` - Update character
- `DELETE /api/characters/{id}` - Delete character

### Narrative
- `GET /api/projects/{id}/scenes` - List scenes
- `POST /api/projects/{id}/scenes` - Create scene
- `GET /api/projects/{id}/timeline` - Get timeline
- `GET /api/projects/{id}/relationships` - Get relationship graph

### Consistency
- `POST /api/consistency/check` - Run consistency check
- `GET /api/consistency/warnings` - Get warnings
- `POST /api/consistency/resolve` - Resolve conflict

### Export
- `POST /api/export/pdf` - Export to PDF
- `POST /api/export/docx` - Export to DOCX
- `POST /api/export/markdown` - Export to Markdown
- `POST /api/export/epub` - Export to EPUB

### WebSocket
- `WS /ws/collaboration/{project_id}` - Real-time collaboration

## Response Format

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation successful"
}
```

### Error Response
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": { ... }
  }
}
```

## Rate Limiting
- 100 requests per minute per user
- 1000 requests per hour per user
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`
