import os
import json
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def get_authenticated_service():
    client_id = os.environ["YT_CLIENT_ID"]
    client_secret = os.environ["YT_CLIENT_SECRET"]
    refresh_token = os.environ["YT_REFRESH_TOKEN"]

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.readonly"]
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)

def fetch_channel_passport(youtube):
    # 1. Fetch static channel info & uploads playlist
    ch_req = youtube.channels().list(
        part="snippet,contentDetails,statistics",
        mine=True
    )
    ch_res = ch_req.execute()
    
    if not ch_res.get("items"):
        raise RuntimeError("No channel found for authenticated user.")

    ch_data = ch_res["items"][0]
    channel_id = ch_data["id"]
    uploads_id = ch_data["contentDetails"]["relatedPlaylists"]["uploads"]

    passport = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "channel_identity": {
            "channel_id": channel_id,
            "title": ch_data["snippet"]["title"],
            "handle": ch_data["snippet"].get("customUrl", "N/A"),
            "published_at": ch_data["snippet"]["publishedAt"],
            "country": ch_data["snippet"].get("country", "N/A"),
            "total_video_count": ch_data["statistics"].get("videoCount"),
            "subscriber_count_approx": ch_data["statistics"].get("subscriberCount")
        },
        "recent_activity": {
            "last_upload": None,
            "last_completed_stream": None
        },
        "manual_vault_records": {
            "adsense_publisher_id": os.environ.get("VAULT_ADSENSE_PUB_ID", "Not Configured"),
            "adsense_login_email": os.environ.get("VAULT_ADSENSE_EMAIL", "Not Configured"),
            "brand_account_id": os.environ.get("VAULT_BRAND_ACCOUNT_ID", "Not Configured"),
            "primary_isp_city": os.environ.get("VAULT_PRIMARY_ISP_CITY", "Not Configured")
        }
    }

    # 2. Fetch last uploaded video
    up_req = youtube.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=uploads_id,
        maxResults=1
    )
    up_res = up_req.execute()
    if up_res.get("items"):
        item = up_res["items"][0]
        passport["recent_activity"]["last_upload"] = {
            "video_id": item["contentDetails"]["videoId"],
            "title": item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"]
        }

    # 3. Fetch last completed live stream
    stream_req = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        type="video",
        eventType="completed",
        order="date",
        maxResults=1
    )
    stream_res = stream_req.execute()
    if stream_res.get("items"):
        st = stream_res["items"][0]
        passport["recent_activity"]["last_completed_stream"] = {
            "video_id": st["id"]["videoId"],
            "title": st["snippet"]["title"],
            "published_at": st["snippet"]["publishedAt"]
        }

    return passport

def send_passport_email(passport):
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASSWORD"]
    to_email = os.environ["RECOVERY_ALERT_EMAIL"]

    subject = f"🛡️ YouTube Channel Recovery Snapshot: {passport['channel_identity']['title']} ({passport['channel_identity']['channel_id']})"
    
    html_body = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #111;">
      <h2 style="color: #0b57d0; border-bottom: 2px solid #0b57d0; padding-bottom: 8px;">YouTube Channel Recovery Passport</h2>
      <p style="color: #666; font-size: 13px;">Generated automatically on {passport['generated_at_utc']}</p>
      
      <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
        <tr style="background: #f1f3f4;"><th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Field</th><th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Value Required for Hijack Form</th></tr>
        <tr><td style="padding: 8px; border: 1px solid #ddd;"><b>Canonical Channel ID</b></td><td style="padding: 8px; border: 1px solid #ddd; font-family: monospace; font-size: 14px; font-weight: bold; color: #d93025;">{passport['channel_identity']['channel_id']}</td></tr>
        <tr><td style="padding: 8px; border: 1px solid #ddd;">Channel Handle</td><td style="padding: 8px; border: 1px solid #ddd;">{passport['channel_identity']['handle']}</td></tr>
        <tr><td style="padding: 8px; border: 1px solid #ddd;">Channel Creation Date</td><td style="padding: 8px; border: 1px solid #ddd;">{passport['channel_identity']['published_at']}</td></tr>
        <tr><td style="padding: 8px; border: 1px solid #ddd;">AdSense Publisher ID</td><td style="padding: 8px; border: 1px solid #ddd; font-family: monospace;">{passport['manual_vault_records']['adsense_publisher_id']}</td></tr>
        <tr><td style="padding: 8px; border: 1px solid #ddd;">AdSense Associated Email</td><td style="padding: 8px; border: 1px solid #ddd;">{passport['manual_vault_records']['adsense_login_email']}</td></tr>
        <tr><td style="padding: 8px; border: 1px solid #ddd;">Brand Account ID</td><td style="padding: 8px; border: 1px solid #ddd; font-family: monospace;">{passport['manual_vault_records']['brand_account_id']}</td></tr>
        <tr><td style="padding: 8px; border: 1px solid #ddd;">Primary Production Location / ISP</td><td style="padding: 8px; border: 1px solid #ddd;">{passport['manual_vault_records']['primary_isp_city']}</td></tr>
      </table>

      <h3 style="margin-top: 25px; color: #333;">Last Known Legitimate Activity</h3>
      <table style="width: 100%; border-collapse: collapse;">
        <tr style="background: #f8f9fa;"><th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Type</th><th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Title</th><th style="padding: 8px; text-align: left; border: 1px solid #ddd;">ID / Link</th></tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;">Last Upload</td>
          <td style="padding: 8px; border: 1px solid #ddd;">{passport['recent_activity']['last_upload']['title'] if passport['recent_activity']['last_upload'] else 'None'}</td>
          <td style="padding: 8px; border: 1px solid #ddd; font-family: monospace;">{passport['recent_activity']['last_upload']['video_id'] if passport['recent_activity']['last_upload'] else 'N/A'}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;">Last Stream</td>
          <td style="padding: 8px; border: 1px solid #ddd;">{passport['recent_activity']['last_completed_stream']['title'] if passport['recent_activity']['last_completed_stream'] else 'None'}</td>
          <td style="padding: 8px; border: 1px solid #ddd; font-family: monospace;">{passport['recent_activity']['last_completed_stream']['video_id'] if passport['recent_activity']['last_completed_stream'] else 'N/A'}</td>
        </tr>
      </table>
      
      <p style="margin-top: 25px; font-size: 12px; color: #777;">Keep this email safe outside your primary Google account. If your channel is compromised, use the Canonical Channel ID to contact @TeamYouTube immediately.</p>
    </body>
    </html>
    """

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email

    # HTML Body
    msg.attach(MIMEText(html_body, "html"))

    # JSON Attachment
    raw_json = json.dumps(passport, indent=2)
    part = MIMEApplication(raw_json, Name="channel_vault_snapshot.json")
    part["Content-Disposition"] = 'attachment; filename="channel_vault_snapshot.json"'
    msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_email], msg.as_string())

if __name__ == "__main__":
    yt = get_authenticated_service()
    data = fetch_channel_passport(yt)
    send_passport_email(data)
    print("Recovery passport generated and dispatched successfully.")