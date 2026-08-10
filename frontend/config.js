// Default API base URL used when the browser has no saved override.
// Point this at your FastAPI backend (e.g. http://localhost:8000 for a
// local `uvicorn src.main:app --reload` run, or your ALB DNS name once
// deployed - infra/s3_frontend_website.tf generates a deployed copy of
// this file with the real ALB address baked in, so you don't need to
// edit this checked-in copy for that).
window.TICKETDESK_DEFAULT_API_BASE = "http://localhost:8000";
