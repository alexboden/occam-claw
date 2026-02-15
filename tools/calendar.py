from datetime import datetime, timedelta, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service(creds_path: str):
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds)


def list_events(creds_path: str, calendar_id: str, days: int = 7) -> list[dict]:
    service = _get_service(creds_path)
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    result = service.events().list(
        calendarId=calendar_id,
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return [
        {
            "id": e["id"],
            "summary": e.get("summary", "(no title)"),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date")),
            "location": e.get("location", ""),
            "description": e.get("description", ""),
        }
        for e in result.get("items", [])
    ]


def create_event(creds_path: str, calendar_id: str, summary: str, start: str, end: str, description: str = "", timezone: str = "America/Toronto") -> dict:
    service = _get_service(creds_path)
    event = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
    }
    if description:
        event["description"] = description
    created = service.events().insert(calendarId=calendar_id, body=event).execute()
    return {"id": created["id"], "summary": created["summary"], "link": created["htmlLink"]}


def update_event(creds_path: str, calendar_id: str, event_id: str, **updates) -> dict:
    service = _get_service(creds_path)
    existing = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    for key in ("summary", "description", "location"):
        if key in updates:
            existing[key] = updates[key]
    if "start" in updates:
        existing["start"]["dateTime"] = updates["start"]
    if "end" in updates:
        existing["end"]["dateTime"] = updates["end"]
    updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=existing).execute()
    return {"id": updated["id"], "summary": updated["summary"], "link": updated["htmlLink"]}
