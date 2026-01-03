import discord
from discord.ext import commands, tasks
import json
import os
import re # 数字の計算のために追加
from datetime import datetime, time, timedelta
from keep_alive import keep_alive # クラウド用

# ==========================================
# ★設定エリア
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1456238358761181310 # 数字のIDを入れてください

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

DATA_FILE = "tasks.json"

# --- データを読み書きする関数 (構造変更) ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                pass
    # 初期データ構造
    return {"one_time": {}, "weekly": {}, "monthly": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- Bot起動時 ---
@bot.event
async def on_ready():
    print(f'PowerUp Bot ログイン: {bot.user}')
    check_schedule.start()

# --- 機能1: 期間指定タスク分配 ---
# 例: !task 2025/01/04-2025/01/07 レポート8000字
@bot.command()
async def task(ctx, date_range, *, content):
    try:
        # 1. 期間を解析する
        start_str, end_str = date_range.split('-')
        start_date = datetime.strptime(start_str, '%Y/%m/%d')
        end_date = datetime.strptime(end_str, '%Y/%m/%d')
        
        # 日数を計算 (開始日も含めるので +1)
        days_count = (end_date - start_date).days + 1
        
        if days_count <= 0:
            await ctx.send("エラー: 終了日は開始日よりあとにしてください。")
            return

        # 2. 数字が含まれているか探し、割り算する
        # 正規表現で数字を抽出
        match = re.search(r'(\d+)', content)
        task_text_base = content
        
        # 数字があれば割り算を試みる
        if match:
            total_num = int(match.group(1))
            daily_num = total_num // days_count # 整数で割る
            # 元のテキストの数字部分を、1日分の数字に置き換える
            task_text_base = content.replace(str(total_num), str(daily_num))
            msg_extra = f" (合計 {total_num} ÷ {days_count}日)"
        else:
            msg_extra = ""

        # 3. データを保存
        data = load_data()
        current_date = start_date
        
        for i in range(days_count):
            date_key = current_date.strftime('%Y/%m/%d')
            
            # 日付ごとのテキストを作成
            daily_text = f"{task_text_base} {msg_extra} [Day {i+1}/{days_count}]"
            
            if date_key not in data["one_time"]:
                data["one_time"][date_key] = []
            data["one_time"][date_key].append(daily_text)
            
            # 次の日へ
            current_date += timedelta(days=1)

        save_data(data)
        await ctx.send(f"✅ **{days_count}日間** のタスクを登録しました！\n1日あたり: {task_text_base}")

    except ValueError:
        await ctx.send("エラー: 日付形式は `2025/01/01-2025/01/03` のように入力してください。")

# --- 機能2: 繰り返し予定 ---
# 例: !repeat Tue/Sat 買い物
# 例: !repeat 15/25 銀行へ行く
@bot.command(name="repeat") # !repeat コマンド
async def schedule_repeat(ctx, days_str, *, content):
    data = load_data()
    targets = days_str.split('/')
    
    registered = []
    
    # 曜日変換用マップ
    week_map = {"Sun": "Sunday", "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday"}
    
    for t in targets:
        # 数字なら「毎月」、文字なら「毎週」と判断
        if t.isdigit(): # 毎月 (1〜31)
            day_num = str(int(t)) # 01 -> 1 に直す
            if day_num not in data["monthly"]:
                data["monthly"][day_num] = []
            data["monthly"][day_num].append(content)
            registered.append(f"毎月{day_num}日")
            
        elif t in week_map: # 毎週 (Tueなど)
            if t not in data["weekly"]:
                data["weekly"][t] = []
            data["weekly"][t].append(content)
            registered.append(f"毎週{week_map[t]}")
            
        else:
            await ctx.send(f"⚠️ `{t}` は無効な指定です。(Tue または 15 のように指定)")
            continue

    save_data(data)
    if registered:
        await ctx.send(f"🔄 繰り返し予定を登録しました: {', '.join(registered)} -> 「{content}」")

# --- 定期通知機能（毎朝チェック） ---
@tasks.loop(minutes=1)
async def check_schedule():
    now = datetime.now()
    target_time = time(7, 0) # 朝7時に通知
    
    if now.hour == target_time.hour and now.minute == target_time.minute:
        today_date = now.strftime('%Y/%m/%d') # 2025/01/04
        today_day = str(now.day)              # 4
        today_weekday = now.strftime('%a')    # Sat
        
        data = load_data()
        tasks_today = []

        # 1. 単発タスク (one_time)
        if today_date in data["one_time"]:
            tasks_today.extend(data["one_time"][today_date])
        
        # 2. 毎週タスク (weekly)
        if today_weekday in data["weekly"]:
            tasks_today.extend(data["weekly"][today_weekday])
            
        # 3. 毎月タスク (monthly)
        if today_day in data["monthly"]:
            tasks_today.extend(data["monthly"][today_day])

        # 通知処理
        channel = bot.get_channel(CHANNEL_ID)
        if channel and tasks_today:
            task_list = "\n".join([f"・{t}" for t in tasks_today])
            await channel.send(f"☀️ **おはようございます！ {today_date} ({today_weekday})**\n本日のタスクです：\n{task_list}")
        elif channel:
             # タスクがない日も通知したい場合はコメントアウトを外す
             # await channel.send(f"☀️ {today_date} 本日のタスクはありません。")
             pass

@check_schedule.before_loop
async def before_check():
    await bot.wait_until_ready()

# Bot実行
keep_alive()
bot.run(TOKEN)