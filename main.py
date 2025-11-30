import os
import requests
import yt_dlp
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# إعدادات التسجيل - Logger Configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# يتم جلب التوكن من متغير البيئة
TOKEN = os.environ.get("TOKEN")

if not TOKEN:
    logger.error("ERROR: TOKEN environment variable not set. Please set the 'TOKEN'.")
    exit(1)

# دالة تحميل الفيديو من يوتيوب باستخدام yt-dlp - Downloads video from YouTube
def download_youtube(url):
    # استخدام المسار المؤقت /tmp الذي يُسمح بالكتابة فيه في البيئات السحابية
    temp_path = '/tmp/'
    ydl_opts = {
        # يضمن وجود اسم ملف فريد وآمن في المسار المؤقت
        'outtmpl': os.path.join(temp_path, '%(id)s.%(ext)s'),
        # اختيار أفضل جودة فيديو وصوت متاحة وتوحيدها في MP4
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4', 
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        # حد أقصى للحجم (50MB) لتجنب التحميلات الكبيرة جدًا التي قد تفشل في الإرسال للتيليجرام
        'max_filesize': 50 * 1024 * 1024, 
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # إرجاع مسار الملف النهائي بعد التحميل
        return ydl.prepare_filename(info)

# دالة استخراج رابط التحميل من إنستجرام - Extracts download link from Instagram
def get_instagram_download(url):
    api = f"https://saveinsta.app/api/lookup/?url={url}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(api, headers=headers, timeout=15)
        resp.raise_for_status() 
        data = resp.json()
        
        if data and data.get("media"):
            return data["media"][0].get("downloadUrl")
        return None
    except requests.RequestException as e:
        logger.error(f"Error fetching Instagram API: {e}")
        return None
    except Exception as e:
        logger.error(f"Error processing Instagram JSON: {e}")
        return None

# دالة معالجة الرسائل - Handles incoming text messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # إذا لم تكن هناك رسالة نصية، نتجاهل الرسالة
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip()
    file_path = None # تعريف المسار خارج نطاق try-finally
    
    try:
        # إظهار أن البوت يكتب
        await update.message.reply_chat_action("typing")

        if "youtube.com" in text or "youtu.be" in text:
            await update.message.reply_text("جاري تحميل الفيديو من YouTube... قد يستغرق الأمر بعض الوقت.")
            
            # التحميل يتم في دالة متزامنة (Blocking call)
            # يتم تشغيله في مجمع الخيوط (Thread pool) لتجنب حظر الحلقة الرئيسية (Event loop)
            file_path = await context.application.loop.run_in_executor(
                None, download_youtube, text
            )

            # الإرسال
            await update.message.reply_video(
                video=file_path, 
                caption="✅ تم التحميل بنجاح!", 
            )

        elif "instagram.com" in text:
            await update.message.reply_text("جاري استخراج رابط التحميل من Instagram...")
            
            dl_url = get_instagram_download(text)
            
            if dl_url:
                # يرسل الفيديو مباشرة من الرابط، لا يحتاج لملف محلي
                await update.message.reply_video(
                    video=dl_url, 
                    caption="✅ تم التحميل بنجاح!"
                )
            else:
                await update.message.reply_text("معلش، مينفعش أجيب الفيديو دلوقتي. (قد يكون الرابط غير صالح، خاص، أو الـ API غير متوفر).")

        else:
            # رسالة الترحيب والتعليمات
            await update.message.reply_text("مرحبًا بك في بوت التنزيل! ابعت لينك فيديو من YouTube أو Instagram بس.")

    except TelegramError as te:
        logger.error(f"Telegram Error sending video: {te}")
        await update.message.reply_text("حدث خطأ أثناء إرسال الفيديو للتيليجرام. (قد يكون حجم الفيديو كبيرًا جدًا).")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        await update.message.reply_text("حصل خطأ غير متوقع في التحميل. جرب تاني أو ابعت لينك تاني.")

    finally:
        # التأكد من حذف الملف المؤقت بعد الاستخدام
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up file: {file_path}")
            except Exception as e:
                logger.error(f"Error cleaning up file: {e}")


def main():
    """بدء تشغيل البوت."""
    # بناء التطبيق باستخدام التوكن
    application = Application.builder().token(TOKEN).build()

    # إضافة معالج الرسائل: يستجيب للنصوص التي ليست أوامر
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting bot polling...")
    # بدء تشغيل البوت في وضعية الاستقصاء (Polling)
    # ملاحظة: في بيئات السحابة مثل Railway، يفضل استخدام Webhooks
    # ولكن polling أسهل للتشغيل الأولي
    application.run_polling(poll_interval=3.0)

if __name__ == "__main__":
    main()