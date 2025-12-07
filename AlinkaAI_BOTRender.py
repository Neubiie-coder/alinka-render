import telebot
from telebot import types
import google.generativeai as genai
import time
import requests
import io
import os
from flask import Flask
from threading import Thread

# ================= KONFIGURASI DARI ENVIRONMENT (RENDER) =================
# Kunci rahasia diambil dari settingan Render (Environment Variables)
# JANGAN TULIS TOKEN DISINI AGAR AMAN SAAT UPLOAD KE GITHUB
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
HUGGINGFACE_TOKEN = os.environ.get("HUGGINGFACE_TOKEN")

# Setup AI
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Konfigurasi Hugging Face (Model FLUX.1-dev)
HF_API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev"
headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}

# Memory Chat (Ingatan Bot)
user_sessions = {}

# ================= SERVER PENYAMARAN (FLASK) =================
# Ini trik agar Render menganggap bot kita adalah Website, jadi tidak dimatikan.
app = Flask('')

@app.route('/')
def home():
    return "Halo! Bot Alinka sedang berjalan di Render. (Status: Online 🟢)"

def run_web():
    # Render memberikan PORT otomatis, kita wajib pakai itu
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ================= FUNGSI PELUKIS (HUGGING FACE) =================
def query_huggingface(payload):
    # Fungsi ini sabar menunggu jika model sedang loading (Error 503)
    retry_count = 0
    while retry_count < 5:
        response = requests.post(HF_API_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.content
        elif response.status_code == 503:
            # Model tidur, tunggu 5 detik
            time.sleep(5)
            retry_count += 1
        else:
            print(f"Error HF: {response.text}")
            return None
    return None

# ================= MENU BOT =================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_sutradara = types.KeyboardButton('🎬 Mode Sutradara')
    btn_curhat = types.KeyboardButton('💬 Ngobrol Santai')
    btn_reset = types.KeyboardButton('♻️ Reset Ingatan')
    markup.add(btn_sutradara, btn_curhat, btn_reset)
    
    # Hapus ingatan lama saat restart
    if message.chat.id in user_sessions: del user_sessions[message.chat.id]
    
    bot.reply_to(message, f"Halo {message.from_user.first_name}! 👋\nSaya Alinka (Versi Cloud Render).\nSiap membuat Naskah & Poster Video!", reply_markup=markup)

# ================= LOGIKA UTAMA =================
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text
    chat_id = message.chat.id
    
    # Init Memory jika belum ada
    if chat_id not in user_sessions: 
        user_sessions[chat_id] = model.start_chat(history=[])
    chat_session = user_sessions[chat_id]

    # Reset Ingatan
    if user_text == "♻️ Reset Ingatan":
        user_sessions[chat_id] = model.start_chat(history=[])
        bot.reply_to(message, "Ingatan dihapus! Mulai dari nol. 🤯")
        return

    # --- LOGIKA SUTRADARA (VIDEO & GAMBAR) ---
    keywords = ["sutradara", "buatkan prompt", "bikin konsep", "gambar", "poster", "ide video"]
    is_director_mode = "Mode Sutradara" in user_text or any(k in user_text.lower() for k in keywords)
    
    if is_director_mode and "Ngobrol Santai" not in user_text:
        
        if user_text == "🎬 Mode Sutradara":
            bot.reply_to(message, "Siap! 🎬\nSilakan ketik ide videomu. (Contoh: 'Kucing astronot di bulan')")
            return

        try:
            bot.send_chat_action(chat_id, 'typing')

            # 1. BUAT NASKAH (GEMINI)
            prompt_system = f"""
            [ROLE: VIDEO DIRECTOR]
            User Request: '{user_text}'
            Output Format:
            1. 🇮🇩 KONSEP (Indo)
            2. 🎬 PROMPT VISUAL (English - Detail, Cinematic, 8k)
            """
            response = chat_session.send_message(prompt_system)
            reply_text = response.text
            
            # Kirim teks (potong jika kepanjangan)
            if len(reply_text) > 4000:
                bot.send_message(chat_id, reply_text[:4000])
            else:
                bot.reply_to(message, reply_text)
            
            # 2. BUAT GAMBAR (HUGGING FACE FLUX)
            bot.send_chat_action(chat_id, 'upload_photo')
            msg_loading = bot.send_message(chat_id, "🎨 Sedang melukis di server Cloud... (Tunggu sebentar)")
            
            # Tambahkan bumbu prompt biar makin bagus
            img_prompt = user_text + ", cinematic, photorealistic, 8k, highly detailed, masterpiece, sharp focus"
            
            img_bytes = query_huggingface({"inputs": img_prompt})
            
            if img_bytes:
                # Kirim Gambar Langsung
                bot.send_photo(chat_id, io.BytesIO(img_bytes), caption="📸 Created on Render (FLUX.1-dev)")
                bot.delete_message(chat_id, msg_loading.message_id)
            else:
                bot.delete_message(chat_id, msg_loading.message_id)
                bot.send_message(chat_id, "⚠️ Server gambar lagi penuh sesak. Coba sesaat lagi.")

        except Exception as e:
            bot.reply_to(message, f"Maaf, ada gangguan sistem: {e}")

    # --- LOGIKA NGOBROL BIASA ---
    else:
        try:
            bot.send_chat_action(chat_id, 'typing')
            response = chat_session.send_message(user_text)
            bot.reply_to(message, response.text)
        except:
             user_sessions[chat_id] = model.start_chat(history=[])
             bot.reply_to(message, "Maaf, aku lupa tadi ngomong apa. Ulangi dong.")

# ================= JALANKAN SERVER & BOT =================
if __name__ == "__main__":
    keep_alive() # Nyalakan server palsu dulu
    print("Bot Render Berjalan...")
    bot.infinity_polling()
