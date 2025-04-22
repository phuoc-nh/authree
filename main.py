from datetime import datetime
from io import BytesIO
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import os
import boto3
from typing import List
import face_recognition
load_dotenv()
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecret")

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={"scope": "openid email profile"},
)

# SESSION login
@app.get("/")
async def homepage(request: Request):
    user = request.session.get("user")
    print("user >>>>>", user)    
    if user:
        return HTMLResponse(
            f"""
            <h1>Welcome {user['email']}</h1>
            <a href='/logout'>Logout</a><br>
            <a href='/attendance-form'>Submit Attendance</a><br>
            <a href='/upload-form'>Upload Face</a>
            """
        )
    return HTMLResponse("<a href='/login'>Login with Google</a>")

@app.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("auth")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth")
async def auth(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")  # SAFE way to extract user info
    if not user:
        return HTMLResponse("<h1>Authentication failed: No user info</h1>")

    print("user", user)
    request.session["user"] = dict(user)

    user_id = user.get("sub")  # or email
    print("user_id", user_id)

    # Choose one:
    create_user_directory_s3(user_id)
    # create_user_directory_supabase(user_id)

    return RedirectResponse(url="/")

@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")

def create_user_directory_s3(user_id: str):
    print("user_id", user_id)
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    
    print("Creating S3 bucket folder for user:", user_id)
    # Ensure the bucket exists

    bucket = os.getenv("AWS_S3_BUCKET")
    prefix = f"faces/{user_id}/"
    s3.put_object(Bucket=bucket, Key=prefix)  # Creates an empty "folder"
    
@app.post("/upload-face")
async def upload_face_image(request: Request, files: List[UploadFile] = File(...)):
    user = request.session.get("user")
    print("user", user)
    if not user or "sub" not in user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = user["sub"]
    uploaded_urls = []

    for file in files:
        contents = await file.read()

        # Generate timestamp-based filename
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        filename = f"faces/{user_id}/{timestamp}.jpg"

        # Upload to S3
        url = upload_to_s3(contents, filename)
        uploaded_urls.append(url)

    return {
        # "message": f"Uploaded {len(uploaded_urls)} image(s) for user {user_id}",
        # "urls": uploaded_urls
        "success": True,
    }
    
def upload_to_s3(file_data, filename):
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    
    # Ensure the bucket exists

    bucket = os.getenv("AWS_S3_BUCKET")

    s3.put_object(Bucket=bucket, Key=filename, Body=file_data, ContentType="image/jpeg")

@app.get("/upload-form", response_class=HTMLResponse)
async def upload_form():
    return """
    <html>
        <head>
            <title>Upload Image</title>
        </head>
        <body>
            <h1>Upload an Image</h1>
            <form action="/upload-face" enctype="multipart/form-data" method="post" >
                <input name="files" type="file" accept="image/*" multiple>
                <input type="submit" value="Upload">
            </form>
        </body>
    </html>
    """
    

def get_user_faces_from_s3(user_id: str):
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
    )

    bucket = os.getenv("AWS_S3_BUCKET")
    prefix = f"faces/{user_id}/"

    result = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if "Contents" not in result:
        return [], []

    known_encodings = []
    known_names = []

    for obj in result["Contents"]:
        key = obj["Key"]
        if key.endswith((".jpg", ".jpeg", ".png")):
            response = s3.get_object(Bucket=bucket, Key=key)
            image_data = response["Body"].read()
            image = face_recognition.load_image_file(BytesIO(image_data))
            encodings = face_recognition.face_encodings(image)

            if encodings:
                known_encodings.append(encodings[0])
                known_names.append(user_id)

    return known_encodings, known_names


@app.post("/attendance")
async def mark_attendance(request: Request, file: UploadFile = File(...)):
    user = request.session.get("user")
    if not user or "sub" not in user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = user["sub"]
    contents = await file.read()

    unknown_image = face_recognition.load_image_file(BytesIO(contents))
    unknown_encodings = face_recognition.face_encodings(unknown_image)

    if not unknown_encodings:
        raise HTTPException(status_code=400, detail="No face found in uploaded image.")

    unknown_encoding = unknown_encodings[0]

    # Load this user's stored face images
    known_encodings, known_names = get_user_faces_from_s3(user_id)

    if not known_encodings:
        raise HTTPException(status_code=404, detail="No stored faces found for this user.")

    results = face_recognition.compare_faces(known_encodings, unknown_encoding, tolerance=0.5)

    if any(results):
        # save_attendance(user_id)  # or user["email"] if you want email
        return {"message": f"Attendance marked for user {user_id}"}

    raise HTTPException(status_code=404, detail="Face not recognized.")


@app.get("/attendance-form", response_class=HTMLResponse)
async def attendance_form():
    return """
    <html>
        <head>
            <title>Face Attendance</title>
        </head>
        <body>
            <h1>Submit Your Face for Attendance</h1>
            <form action="/attendance" enctype="multipart/form-data" method="post">
                <input name="file" type="file" accept="image/*" required>
                <br><br>
                <input type="submit" value="Submit Attendance">
            </form>
        </body>
    </html>
    """