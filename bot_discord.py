import os
import discord
from discord.ext import commands
import requests
import qrcode
import io
import re
import time
import uuid

# 🆔 Unique bot instance identifier
BOT_INSTANCE_ID = str(uuid.uuid4())[:8]

# ⚠️ Thay bằng token bot thật của bạn
TOKEN = os.getenv("DISCORD_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 🕒 Lưu trữ các link đã xử lý để tránh trùng lặp
processed_links = {}
processed_messages = set()  # Lưu trữ ID các message đã xử lý
LINK_COOLDOWN = 30  # 30 giây cooldown cho mỗi link

# 🔍 Mở rộng link rút gọn dạng shp.ee hoặc vn.shp.ee
def expand_url(short_url):
    try:
        res = requests.head(short_url, allow_redirects=True, timeout=5)
        return res.url if res.status_code == 200 else None
    except:
        return None

# 🔗 Rút gọn link qua AccessTrade
def shorten_shopee_link(original_url):
    campaign_id = get_shopee_campaign_id()
    if not campaign_id:
        return None

    url = "https://api.accesstrade.vn/v1/product_link/create"
    headers = {
        "Authorization": f"Token {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "campaign_id": campaign_id,
        "urls": [original_url]
    }

    res = requests.post(url, headers=headers, json=data)
    if res.status_code == 200:
        json_data = res.json()
        if json_data["success"]:
            return json_data["data"]["success_link"][0]["short_link"]
    return None

# 📦 Lấy campaign ID của Shopee
def get_shopee_campaign_id():
    url = "https://api.accesstrade.vn/v1/campaigns?approval=successful"
    headers = {"Authorization": f"Token {ACCESS_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        for campaign in res.json()["data"]:
            if campaign["merchant"] == "shopee":
                return campaign["id"]
    return None

# 🖼️ Tạo mã QR
def generate_qr_code(url):
    qr = qrcode.make(url)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# ✅ Bot khởi động
@bot.event
async def on_ready():
    print(f'✅ Bot đã sẵn sàng: {bot.user} [Instance: {BOT_INSTANCE_ID}]')
    print(f'🔧 Bot instance ID: {BOT_INSTANCE_ID}')

# ✅ Lệnh thủ công: !rutgon <link>
@bot.command()
async def rutgon(ctx, *, link: str):
    await process_link(ctx.channel, link)

# 📊 Lệnh kiểm tra trạng thái bot
@bot.command()
async def status(ctx):
    status_text = "🤖 **Trạng thái Bot Shopee**\n\n"
    status_text += f"✅ **Bot đang hoạt động**: {bot.user.name}\n"
    status_text += f"🔗 **Rút gọn link**: ✅ Hoạt động\n"
    status_text += f"🎯 **Tạo QR code**: ✅ Hoạt động\n"
    
    status_text += f"\n🎮 **Lệnh khả dụng:**\n"
    status_text += f"• `!rutgon <link>` - Rút gọn link thủ công\n"
    status_text += f"• `!status` - Kiểm tra trạng thái bot\n"
    status_text += f"• Gửi link Shopee - Tự động xử lý\n"
    
    await ctx.send(status_text)

# 📩 Tự động nhận diện mọi link shopee
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Cleanup processed_messages để tránh tốn bộ nhớ (giữ lại 1000 message gần nhất)
    if len(processed_messages) > 1000:
        # Xóa 500 message cũ nhất (giả sử ID nhỏ hơn là cũ hơn)
        old_messages = sorted(processed_messages)[:500]
        for old_id in old_messages:
            processed_messages.discard(old_id)
        print(f"🧹 [{BOT_INSTANCE_ID}] Đã dọn dẹp {len(old_messages)} message cũ")

    # Kiểm tra xem message đã được xử lý chưa
    if message.id in processed_messages:
        print(f"⚠️ [{BOT_INSTANCE_ID}] Message {message.id} đã được xử lý, bỏ qua")
        return
    
    # Đánh dấu message đã xử lý
    processed_messages.add(message.id)
    print(f"📨 [{BOT_INSTANCE_ID}] Nhận tin nhắn mới {message.id} từ {message.author}: {message.content}")
    
    # Nếu là lệnh thì xử lý lệnh
    if message.content.startswith(bot.command_prefix):
        print(f"⚡ [{BOT_INSTANCE_ID}] Đây là lệnh bot, chuyển đến process_commands")
        await bot.process_commands(message)
        return

    # Tìm link Shopee trong tin nhắn
    pattern = r'(https?://(?:shopee\.vn|shp\.ee|vn\.shp\.ee)/\S+)'
    matches = re.findall(pattern, message.content)
    
    print(f"🔍 [{BOT_INSTANCE_ID}] Tìm thấy {len(matches)} link(s): {matches}")
    
    # Chỉ xử lý link đầu tiên để tránh trùng lặp
    if matches:
        link = matches[0]  # Lấy link đầu tiên
        print(f"🚀 [{BOT_INSTANCE_ID}] Bắt đầu xử lý link: {link}")
        await process_link(message.channel, link)

# 🔁 Hàm xử lý link: mở rộng nếu là shp.ee, rồi rút gọn qua AccessTrade
async def process_link(channel, link):
    print(f"🔧 [{BOT_INSTANCE_ID}] process_link được gọi với link: {link}")
    
    # Kiểm tra xem link đã được xử lý gần đây chưa
    current_time = time.time()
    
    # Cleanup các link cũ (quá 30 giây)
    expired_links = [url for url, timestamp in processed_links.items() 
                    if current_time - timestamp > LINK_COOLDOWN]
    for expired_link in expired_links:
        del processed_links[expired_link]
    
    # Kiểm tra link hiện tại
    if link in processed_links:
        time_left = LINK_COOLDOWN - (current_time - processed_links[link])
        print(f"⏰ [{BOT_INSTANCE_ID}] Link đã được xử lý gần đây, còn {int(time_left)} giây")
        await channel.send(f"⏰ [{BOT_INSTANCE_ID}] Link này vừa được xử lý. Vui lòng chờ {int(time_left)} giây nữa.")
        return
    
    # Đánh dấu link đang được xử lý
    processed_links[link] = current_time
    print(f"✅ [{BOT_INSTANCE_ID}] Đã đánh dấu link đang xử lý: {link}")
    
    await channel.send(f"🔗 [{BOT_INSTANCE_ID}] Đang xử lý link...")

    # Nếu là dạng rút gọn shp.ee → mở rộng ra link gốc
    if "shp.ee" in link:
        expanded = expand_url(link)
        if not expanded or "shopee.vn" not in expanded:
            await channel.send("❌ Không thể mở rộng link rút gọn hoặc không phải Shopee!")
            return
        link = expanded

    if "shopee.vn" not in link:
        await channel.send("❌ Link không hợp lệ!")
        return

    short_link = shorten_shopee_link(link)
    if not short_link:
        await channel.send("❌ Không thể rút gọn link.")
        return

    qr_image = generate_qr_code(short_link)
    file = discord.File(fp=qr_image, filename="qrcode.png")
    print(f"📤 [{BOT_INSTANCE_ID}] Gửi kết quả QR cho link: {short_link}")
    await channel.send(f"✅ [{BOT_INSTANCE_ID}] Link đã rút gọn:\n{short_link}", file=file)

# 🟢 Khởi chạy bot
bot.run(TOKEN)
