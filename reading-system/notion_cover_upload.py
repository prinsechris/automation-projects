#!/usr/bin/env python3
"""Upload book cover images directly to Notion pages via internal API.
Uses getUploadFileUrl + S3 presigned URL + submitTransaction."""

import json
import os
import sys
import uuid
import urllib.request
import urllib.error
import tempfile


def get_token():
    """Read Notion token_v2 from file."""
    token_path = os.path.expanduser("~/.notion-token")
    with open(token_path) as f:
        return f.read().strip()


def download_image(url, dest_path=None):
    """Download image from URL to local path."""
    if dest_path is None:
        ext = url.rsplit(".", 1)[-1].split("?")[0]
        if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
            ext = "jpg"
        dest_path = os.path.join(tempfile.gettempdir(), f"book_cover.{ext}")

    req = urllib.request.Request(url, headers={"User-Agent": "ReadingSystem/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        with open(dest_path, "wb") as f:
            f.write(resp.read())
    return dest_path


def get_upload_url(token, page_id, filename, content_type="image/jpeg"):
    """Get S3 presigned upload URL from Notion internal API."""
    data = json.dumps({
        "bucket": "secure",
        "name": filename,
        "contentType": content_type,
        "record": {
            "table": "block",
            "id": page_id,
        }
    }).encode()

    req = urllib.request.Request(
        "https://www.notion.so/api/v3/getUploadFileUrl",
        data=data,
        headers={
            "Cookie": f"token_v2={token}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def upload_to_s3(signed_put_url, file_path, content_type="image/jpeg"):
    """Upload file to S3 via presigned PUT URL."""
    with open(file_path, "rb") as f:
        file_data = f.read()

    req = urllib.request.Request(
        signed_put_url,
        data=file_data,
        method="PUT",
        headers={"Content-Type": content_type},
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def set_page_cover(token, page_id, attachment_url):
    """Set page cover via submitTransaction."""
    data = json.dumps({
        "requestId": str(uuid.uuid4()),
        "transactions": [{
            "id": str(uuid.uuid4()),
            "operations": [{
                "pointer": {"table": "block", "id": page_id},
                "path": ["format", "page_cover"],
                "command": "set",
                "args": attachment_url,
            }]
        }]
    }).encode()

    req = urllib.request.Request(
        "https://www.notion.so/api/v3/submitTransaction",
        data=data,
        headers={
            "Cookie": f"token_v2={token}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def upload_cover(page_id, image_url=None, image_path=None):
    """
    Upload a cover image to a Notion page.

    Args:
        page_id: Notion page ID (with dashes)
        image_url: URL to download image from (optional if image_path given)
        image_path: Local path to image (optional if image_url given)

    Returns:
        dict with status and attachment URL
    """
    token = get_token()

    # Download if URL provided
    if image_url and not image_path:
        print(f"Telechargement: {image_url}")
        image_path = download_image(image_url)

    if not image_path or not os.path.exists(image_path):
        return {"error": "Pas d'image trouvee"}

    filename = os.path.basename(image_path)
    # Detect content type
    ext = filename.rsplit(".", 1)[-1].lower()
    content_types = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                     "gif": "image/gif", "webp": "image/webp"}
    content_type = content_types.get(ext, "image/jpeg")

    # Step 1: Get presigned URL
    print(f"Obtention URL S3 pour {filename}...")
    upload_info = get_upload_url(token, page_id, filename, content_type)
    signed_put_url = upload_info["signedPutUrl"]
    attachment_url = upload_info["url"]

    # Step 2: Upload to S3
    print(f"Upload vers S3...")
    status = upload_to_s3(signed_put_url, image_path, content_type)
    if status != 200:
        return {"error": f"Upload S3 echoue: {status}"}

    # Step 3: Set as page cover
    print(f"Mise a jour de la cover Notion...")
    set_page_cover(token, page_id, attachment_url)

    print(f"Cover uploadee avec succes pour {page_id}")
    return {
        "status": "success",
        "attachment_url": attachment_url,
        "signed_get_url": upload_info.get("signedGetUrl", ""),
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python notion_cover_upload.py <page_id> <image_url_or_path>")
        print("Example: python notion_cover_upload.py 325da200-... https://covers.openlibrary.org/b/id/58950-L.jpg")
        sys.exit(1)

    page_id = sys.argv[1]
    source = sys.argv[2]

    if source.startswith("http"):
        result = upload_cover(page_id, image_url=source)
    else:
        result = upload_cover(page_id, image_path=source)

    print(json.dumps(result, indent=2, ensure_ascii=False))
