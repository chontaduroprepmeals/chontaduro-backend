# upload_image.py
# Register upload-image routes into an existing FastAPI `app`.
# Usage: from upload_image import register_upload_routes
#        register_upload_routes(app)

import os
import sqlite3
import datetime
from fastapi import UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

# Optional dependency on cloudinary; we import lazily so the file can be imported
def register_upload_routes(app, db_file_env="APP_DB_FILE"):
    """
    Call this from your main.py after creating `app = FastAPI()`:
        from upload_image import register_upload_routes
        register_upload_routes(app)
    """

    APP_DB_FILE = os.environ.get(db_file_env, "app.db")

    # Try to configure cloudinary if credentials exist
    CLOUDINARY_CONFIGURED = all([
        os.environ.get("CLOUDINARY_CLOUD_NAME"),
        os.environ.get("CLOUDINARY_API_KEY"),
        os.environ.get("CLOUDINARY_API_SECRET"),
    ])
    if CLOUDINARY_CONFIGURED:
        try:
            import cloudinary
            import cloudinary.uploader
            cloudinary.config(
                cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
                api_key=os.environ.get("CLOUDINARY_API_KEY"),
                api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
                secure=True,
            )
        except Exception as e:
            # If cloudinary not installed, we'll still allow local uploads (see below)
            CLOUDINARY_CONFIGURED = False

    def insert_image_record(url, width=None, height=None, fmt=None, filesize=None,
                            meal_name=None, template_id=None, source="real", uploaded_by=None,
                            alt_text=None, tags=None):
        conn = sqlite3.connect(APP_DB_FILE)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO images (meal_name, template_id, url, width, height, format, filesize, source, uploaded_by, alt_text, tags, uploaded_at, approved)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                meal_name, template_id, url, width, height, fmt, filesize, source, uploaded_by, alt_text, tags,
                datetime.datetime.utcnow().isoformat(), 0
            ))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    @app.post("/upload-image")
    async def upload_image(
        meal_name: str | None = Form(None),
        template_id: str | None = Form(None),
        source: str = Form("real"),
        uploaded_by: str | None = Form(None),
        alt_text: str | None = Form(None),
        tags: str | None = Form(None),
        file: UploadFile = File(...)
    ):
        # Basic validation
        if not file:
            raise HTTPException(status_code=400, detail="No file uploaded.")

        # If Cloudinary configured and available, upload to Cloudinary
        if CLOUDINARY_CONFIGURED:
            try:
                result = cloudinary.uploader.upload(
                    file.file,
                    folder="prepmeals/",
                    use_filename=True,
                    unique_filename=False,
                    overwrite=False
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Cloudinary upload failed: {e}")
            url = result.get("secure_url")
            width = result.get("width")
            height = result.get("height")
            fmt = result.get("format")
            filesize = result.get("bytes")
            img_id = insert_image_record(
                url=url, width=width, height=height, fmt=fmt, filesize=filesize,
                meal_name=meal_name, template_id=template_id, source="cloudinary", uploaded_by=uploaded_by,
                alt_text=alt_text, tags=tags
            )
            return JSONResponse({"ok": True, "image_id": img_id, "url": url, "meta": {"width": width, "height": height, "format": fmt, "bytes": filesize}})
        else:
            # Fallback: save locally under ./uploads/ and record a local url/path
            UPLOAD_DIR = os.environ.get("LOCAL_UPLOAD_DIR", "uploads")
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            filename = file.filename or f"upload_{datetime.datetime.utcnow().timestamp()}"
            dest_path = os.path.join(UPLOAD_DIR, filename)
            # write file bytes
            with open(dest_path, "wb") as out:
                contents = await file.read()
                out.write(contents)
            filesize = os.path.getsize(dest_path)
            url = f"/{UPLOAD_DIR}/{filename}"
            img_id = insert_image_record(
                url=url, width=None, height=None, fmt=None, filesize=filesize,
                meal_name=meal_name, template_id=template_id, source="local", uploaded_by=uploaded_by,
                alt_text=alt_text, tags=tags
            )
            return JSONResponse({"ok": True, "image_id": img_id, "url": url, "meta": {"bytes": filesize}})