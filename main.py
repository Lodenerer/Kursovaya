import cv2
import yt_dlp
import os
import torch
import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from transformers import pipeline
from PIL import Image

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("[*] Инициализация ИИ-моделей (Анти-спам фильтры активны)...")
deepfake_detector = pipeline("image-classification", model="dima806/deepfake_vs_real_image_detection")
ai_content_detector = pipeline("image-classification", model="umm-maybe/AI-image-detector")

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')


class VideoURL(BaseModel):
    url: str


def download_video(url: str, output_path: str):
    if "/video/" in url and not "/embed/" in url:
        video_id = url.split("/video/")[-1].split("?")[0]
        url = f"https://www.tiktok.com/embed/{video_id}"
        print(f"[*] Ссылка трансформирована в EMBED: {url}")

    ydl_opts = {
        'format': 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.tiktok.com/',
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"[-] Ошибка yt-dlp: {e}")
        return False


def analyze_video(video_path: str):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        fps = 30

    total_frames_in_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration = total_frames_in_video / fps if fps > 0 else 0

    print(f"[*] Длина видео: {round(video_duration, 1)} сек. FPS: {fps}")

    ai_frames_count = 0
    fake_face_count = 0
    total_frames_checked = 0
    total_valid_faces = 0
    CONFIDENCE_THRESHOLD_AI = 0.90
    CONFIDENCE_THRESHOLD_DF = 0.85
    CONSENSUS_RATIO = 0.70
    frame_step = int(fps * 1.0)
    MAX_FRAMES_TO_CHECK = 15
    current_frame = 0

    while cap.isOpened() and total_frames_checked < MAX_FRAMES_TO_CHECK and current_frame < total_frames_in_video:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret:
            break

        total_frames_checked += 1
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_full_frame = Image.fromarray(frame_rgb)
        ai_predictions = ai_content_detector(pil_full_frame)

        score_ai = 0.0
        for pred in ai_predictions:
            label = pred['label'].lower()
            if 'fake' in label or 'ai' in label or 'artificial' in label:
                score_ai = pred['score']
                break

        if score_ai > CONFIDENCE_THRESHOLD_AI:
            ai_frames_count += 1

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(120, 120))

        for (x, y, w, h) in faces:
            pad = int(w * 0.15)
            y1, y2 = max(0, y - pad), min(frame.shape[0], y + h + pad)
            x1, x2 = max(0, x - pad), min(frame.shape[1], x + w + pad)

            face_crop = frame[y1:y2, x1:x2]
            pil_face = Image.fromarray(cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB))
            df_predictions = deepfake_detector(pil_face)

            score_df = 0.0
            for pred in df_predictions:
                if 'fake' in pred['label'].lower():
                    score_df = pred['score']
                    break

            total_valid_faces += 1
            if score_df > CONFIDENCE_THRESHOLD_DF:
                fake_face_count += 1

        print(
            f"[DEBUG] Секунда {int(current_frame / fps)} | Риск ИИ: {round(score_ai * 100, 1)}% | Найдено лиц: {len(faces)}")

        current_frame += frame_step
    cap.release()
    is_ai_generated = (ai_frames_count / total_frames_checked) > CONSENSUS_RATIO if total_frames_checked > 0 else False
    is_deepfake = (fake_face_count / total_valid_faces) > CONSENSUS_RATIO if total_valid_faces > 0 else False

    is_fake_overall = is_ai_generated or is_deepfake

    prob_ai = (ai_frames_count / total_frames_checked) if total_frames_checked > 0 else 0.0
    prob_df = (fake_face_count / total_valid_faces) if total_valid_faces > 0 else 0.0
    max_probability = max(prob_ai, prob_df)
    print(
        f"[*] Итог проверки: Сгенерировано ИИ (кадры): {ai_frames_count}/{total_frames_checked} | Дипфейк (лица): {fake_face_count}/{total_valid_faces}")
    print(f"[*] Вердикт: {'ФЕЙК' if is_fake_overall else 'ОРИГИНАЛ'}")
    return {
        "status": "success",
        "is_fake": is_fake_overall,
        "probability": round(max_probability, 4),
        "analyzed_faces": total_valid_faces,
        "message": "Анализ завершен"
    }


@app.post("/api/analyze")
def analyze(data: VideoURL):
    print(f"\n[*] Получена ссылка от агента: {data.url}")

    unique_filename = f"temp_{uuid.uuid4().hex}.mp4"

    try:
        if download_video(data.url, unique_filename):
            print("[*] Видео скачано. Идет глубокий анализ...")
            result = analyze_video(unique_filename)
            print(f"[*] Результат ИИ: {result}")
            return result
        else:
            return {"status": "error", "message": "Не удалось скачать видео"}
    finally:
        if os.path.exists(unique_filename):
            try:
                os.remove(unique_filename)
                print(f"[*] Временный файл {unique_filename} удален.")
            except Exception as e:
                print(f"[-] Не удалось удалить временный файл: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000) 