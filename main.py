import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

from schemas import Lead
from database import create_document

app = FastAPI(title="The Genistein Project API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LeadResponse(BaseModel):
    id: Optional[str] = None
    status: str
    mailchimp: Optional[str] = None
    hubspot: Optional[str] = None


@app.get("/")
def read_root():
    return {"message": "The Genistein Project API"}


@app.post("/api/leads", response_model=LeadResponse)
def create_lead(lead: Lead):
    try:
        doc_id = create_document("lead", lead)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    mc_status = None
    hs_status = None

    # Optional Mailchimp integration
    MAILCHIMP_API_KEY = os.getenv("MAILCHIMP_API_KEY")
    MAILCHIMP_AUDIENCE_ID = os.getenv("MAILCHIMP_AUDIENCE_ID")
    MAILCHIMP_SERVER_PREFIX = os.getenv("MAILCHIMP_SERVER_PREFIX")  # e.g., us21
    if MAILCHIMP_API_KEY and MAILCHIMP_AUDIENCE_ID and MAILCHIMP_SERVER_PREFIX:
        try:
            url = f"https://{MAILCHIMP_SERVER_PREFIX}.api.mailchimp.com/3.0/lists/{MAILCHIMP_AUDIENCE_ID}/members"
            payload = {
                "email_address": lead.email,
                "status_if_new": "subscribed",
                "status": "subscribed",
                "merge_fields": {
                    "FNAME": lead.first_name,
                    "COUNTRY": (lead.country or "")
                }
            }
            resp = requests.post(url, auth=("anystring", MAILCHIMP_API_KEY), json=payload, timeout=8)
            mc_status = f"{resp.status_code}"
        except Exception as e:
            mc_status = f"error:{str(e)[:60]}"

    # Optional HubSpot integration (Contacts API v3)
    HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
    HUBSPOT_LIST_ID = os.getenv("HUBSPOT_LIST_ID")
    if HUBSPOT_API_KEY:
        try:
            contact_url = "https://api.hubapi.com/crm/v3/objects/contacts"
            headers = {"Authorization": f"Bearer {HUBSPOT_API_KEY}", "Content-Type": "application/json"}
            data = {
                "properties": {
                    "email": lead.email,
                    "firstname": lead.first_name,
                    "country": lead.country or "",
                    "source": lead.source or "landing"
                }
            }
            c_resp = requests.post(contact_url, headers=headers, json=data, timeout=8)
            hs_status = f"{c_resp.status_code}"
            # Optionally add to list
            if HUBSPOT_LIST_ID:
                try:
                    list_url = f"https://api.hubapi.com/contacts/v1/lists/{HUBSPOT_LIST_ID}/add"
                    l_resp = requests.post(list_url, headers=headers, json={"emails": [lead.email]}, timeout=8)
                    hs_status = f"{hs_status}|list:{l_resp.status_code}"
                except Exception as e2:
                    hs_status = f"{hs_status}|list:error:{str(e2)[:40]}"
        except Exception as e:
            hs_status = f"error:{str(e)[:60]}"

    return LeadResponse(id=doc_id, status="ok", mailchimp=mc_status, hubspot=hs_status)


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = getattr(db, 'name', None) or ("✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set")
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:60]}"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
