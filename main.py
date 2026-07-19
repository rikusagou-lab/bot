import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta, timezone

# タイムゾーンの設定（日本時間: JST）
JST = timezone(timedelta(hours=9))
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# 参加者名簿の埋め込み（Embed）を最新状態に更新する共通関数
async def update_list_message(bot):
    if not bot.list_channel_id or not bot.list_message_id:
        return
    channel = bot.get_channel(bot.list_channel_id)
    if channel:
        try:
            msg = await channel.fetch_message(bot.list_message_id)
            current_list_text = "\n".join(bot.player_details.values()) if bot.player_details else "現在、登録者はいません。"
            embed = discord.Embed(
                title="参加者　一覧",
                description=f"現在の登録者（計 {len(bot.player_details)} 名）:\n\n{current_list_text}",
                color=0x9b59b6
            )
            await msg.edit(embed=embed)
        except Exception as e:
            print(f"名簿メッセージの更新に失敗しました: {e}")

# 新しく名簿メッセージを送信する共通関数
async def create_list_message(bot):
    if not bot.list_channel_id:
        return
    channel = bot.get_channel(bot.list_channel_id)
    if channel:
        try:
            current_list_text = "\n".join(bot.player_details.values()) if bot.player_details else "現在、登録者はいません。"
            embed = discord.Embed(
                title="参加者　一覧",
                description=f"現在の登録者（計 {len(bot.player_details)} 名）:\n\n{current_list_text}",
                color=0x9b59b6
            )
            if bot.list_message_id:
                try:
                    old_msg = await channel.fetch_message(bot.list_message_id)
                    await old_msg.delete()
                except discord.NotFound:
                    pass
            new_msg = await channel.send(embed=embed)
            bot.list_message_id = new_msg.id
        except Exception as e:
            print(f"名簿メッセージの新規作成に失敗しました: {e}")


# --- /can で開くエントリー情報入力モーダル ---
class TournamentModal(discord.ui.Modal, title="大会エントリー情報入力"):
    game_id = discord.ui.TextInput(
        label="大会で使用したい名前", 
        placeholder="進行役をやってくださるプレイヤーは名前のはじめに進★をつけてください",
        required=True, max_length=50
    )
    friend_code = discord.ui.TextInput(
        label="フレンドコード", 
        placeholder="例　0000-0000-0000",
        required=True, max_length=30
    )

    def __init__(self, bot_client):
        super().__init__()
        self.bot = bot_client

    async def on_submit(self, interaction: discord.Interaction):
        user_name = self.game_id.value
        code = self.friend_code.value
        user_id = interaction.user.id
        
        await interaction.response.send_message(
            f"✅ 情報を送信しました！内容を確認してください。\n🔹 **大会での名前**: {user_name}\n🔹 **フレンドコード**: {code}", 
            ephemeral=True
        )
        self.bot.player_details[user_id] = f"・{user_name} (フレコ: {code})"
        if self.bot.list_message_id:
            await update_list_message(self.bot)
        else:
            await create_list_message(self.bot)


# --- /drop で開く確認モーダル ---
class DropConfirmModal(discord.ui.Modal, title="大会参加取り消し確認"):
    confirm_input = discord.ui.TextInput(
        label="本当に参加を取り消しますか？", 
        placeholder="取り消す場合「はい」と入力してください。",
        required=True, max_length=10
    )

    def __init__(self, bot_client):
        super().__init__()
        self.bot = bot_client

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        if self.confirm_input.value != "はい":
            await interaction.response.send_message("❌ 入力された言葉が正しくありません。取り消しは行われませんでした。", ephemeral=True)
            return
        if user.id not in self.bot.participants:
            await interaction.response.send_message("❌ あなたは大会にエントリーしていません。", ephemeral=True)
            return

        self.bot.participants.remove(user.id)
        if user.id in self.bot.player_details:
            del self.bot.player_details[user.id]
        
        current_count = len(self.bot.participants)
        await interaction.response.send_message("✅ 大会のエントリーを取り消しました（辞退完了）。", ephemeral=True)
        
        embed = discord.Embed(title="🚪 大会辞退（ドロップ）", description=f"{user.mention} さんが大会を辞退しました。", color=0xe74c3c)
        embed.set_footer(text=f"現在のエントリー総数: {current_count}名")
        await interaction.channel.send(embed=embed)
        await update_list_message(self.bot)


# --- /join ボタンの処理（維持） ---
class JoinButtonView(discord.ui.View):
    def __init__(self, bot_client):
        super().__init__(timeout=None)
        self.bot = bot_client

    @discord.ui.button(label="大会に参加する (Join)", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id in self.bot.participants:
            await interaction.response.send_message(f"❌ {user.display_name} さんは既にエントリーされています！", ephemeral=True)
            return
        self.bot.participants.append(user.id)
        current_count = len(self.bot.participants)
        await interaction.response.send_message(f"✅ 大会へのエントリーが完了しました！（現在の参加者: {current_count}名）", ephemeral=True)
        await interaction.channel.send(f"🏃‍♂️ 【エントリー】**{user.display_name}** さんが参加しました！（現在 {current_count} 名）")

    @discord.ui.button(label="辞退する (Leave)", style=discord.ButtonStyle.red, custom_id="leave_btn")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id not in self.bot.participants:
            await interaction.response.send_message("❌ あなたはエントリーしていません。", ephemeral=True)
            return
        await interaction.response.send_modal(DropConfirmModal(self.bot))


# --- 【新規追加】30分前に登場するチェックインボタンの処理 ---
class CheckInButtonView(discord.ui.View):
    def __init__(self, bot_client):
        super().__init__(timeout=None)
        self.bot = bot_client

    @discord.ui.button(label="チェックインする (Check-In)", style=discord.ButtonStyle.blurple, custom_id="checkin_btn")
    async def checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        
        # エントリーしていないプレイヤーは点呼できない
        if user.id not in self.bot.participants:
            await interaction.response.send_message("❌ あなたは大会にエントリーしていないため、チェックインできません。", ephemeral=True)
            return
            
        # すでにチェックイン済みか確認
        if user.id in self.bot.checked_in_users:
            await interaction.response.send_message("🔹 あなたはすでにチェックインが完了しています！", ephemeral=True)
            return
            
        # チェックイン成功処理
        self.bot.checked_in_users.append(user.id)
        await interaction.response.send_message("✅ チェックインが完了しました！大会開始までそのままお待ちください。", ephemeral=True)
        await interaction.channel.send(f"📍 【点呼】**{user.display_name}** さんがチェックインしました。")


class TournamentBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.monitored_events = [] 
        self.participants = [] 
        self.active_panels = [] 
        self.player_details = {} 
        self.list_message_id = None 
        self.list_channel_id = None 
        
        # 【新規追加】チェックイン関連の管理用変数
        self.checked_in_users = [] 
        self.checkin_message_id = None

    async def setup_hook(self):
        await self.tree.sync()
        self.check_event_timer.start()
        self.add_view(JoinButtonView(self))
        self.add_view(CheckInButtonView(self)) # 再起動時もチェックインボタンを有効化

    @tasks.loop(minutes=1)
    async def check_event_timer(self):
        now = datetime.now(JST)
        
        for e in self.monitored_events:
            # 1. 開始3時間前の処理（公式イベント緑色化 ＆ 最初の案内通知）
            if not e["started"]:
                trigger_3h = e["start_time"] - timedelta(hours=3)
                if now >= trigger_3h:
                    guild = self.get_guild(e["guild_id"])
                    if guild:
                        try:
                            event = await guild.fetch_scheduled_event(e["event_id"])
                            if event and event.status == discord.EventStatus.scheduled:
                                await event.edit(status=discord.EventStatus.active)
                            
                            checkin_channel = self.get_channel(e["checkin_channel_id"])
                            if checkin_channel:
                                embed = discord.Embed(title="⏰ 大会3時間前のお知らせ", description="大会開始の3時間前になりました！\n30分前になると、このチャンネルに「点呼ボタン」が登場します。", color=0xe67e22)
                                await checkin_channel.send(embed=embed)
                            e["started"] = True
                        except Exception as err: print(f"3時間前エラー: {err}")

            # 2. 【新規追加】開始30分前の処理（チェックインボタンの設置）
            if e["started"] and not e["checkin_posted"]:
                trigger_30m = e["start_time"] - timedelta(minutes=30)
                if now >= trigger_30m:
                    checkin_channel = self.get_channel(e["checkin_channel_id"])
                    if checkin_channel:
                        try:
                            # 点呼用のボタンパネルを送信
                            embed = discord.Embed(
                                title="📝 【点呼開始】大会30分前チェックイン",
                                description="大会開始30分前になりました！\nエントリーしているプレイヤーは、**下の青いボタンを押してチェックイン**を完了させてください。\n\n⚠️ **大会開始時刻までに押さなかったプレイヤーは自動的に失格・削除されます。**",
                                color=0x3498db
                            )
                            msg = await checkin_channel.send(embed=embed, view=CheckInButtonView(self))
                            self.checkin_message_id = msg.id
                            e["checkin_posted"] = True
                            print("チェックインボタンを配置しました。")
                        except Exception as err: print(f"30分前エラー: {err}")
client.run（'MTUyNzI5MTgyMTI0MjE5MTkwNQ.G_pLrJ.QyrHB6Du1L8GQmNnHHWqAANK0Ve1rkV0lpTnSY')
