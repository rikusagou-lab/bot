import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class TournamentBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = TournamentBot()

bot.run("YOUR_TOKEN")
    async def setup_hook(self):
        await self.tree.sync()
        self.check_event_timer.start()

    @tasks.loop(minutes=1)
    async def check_event_timer(self):

        now = datetime.now(JST)

        for event in self.monitored_events.copy():

            if event["checkin_posted"]:
                continue

            check_time = event["start_time"] - timedelta(minutes=30)

            if now >= check_time:

                channel = self.get_channel(event["channel_id"])

                if channel is None:
                    continue

                embed = discord.Embed(
                    title="📝 チェックイン開始",
                    description=(
                        f"**大会名**：{event['name']}\n\n"
                        f"大会開始30分前になりました。\n"
                        "参加者は下のボタンを押してチェックインしてください。\n\n"
                        "⚠️開始時刻までにチェックインを行わなかった場合は大会に参加できません。"
                    ),
                    color=0x000000
                )

                await channel.send(
                    embed=embed,
                    view=CheckInButtonView(self)
                )

                event["checkin_posted"] = True
                  @app_commands.command(
        name="start",
        description="大会を開始します（管理者専用）"
    )
    @app_commands.default_permissions(administrator=True)
    async def start(self, interaction: discord.Interaction):

        await interaction.response.send_modal(
            StartTournamentModal(self)
        )
          async def setup_hook(self):

        self.tree.add_command(self.start)

        await self.tree.sync()

        self.check_event_timer.start()
# =========================
# チェックインボタン
# =========================

class CheckInButtonView(discord.ui.View):

    def __init__(self, bot_client):
        super().__init__(timeout=None)
        self.bot = bot_client

    @discord.ui.button(
        label="✅ チェックイン",
        style=discord.ButtonStyle.green,
        custom_id="checkin_button"
    )
    async def checkin(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        user = interaction.user

        if user.id not in self.bot.participants:

            await interaction.response.send_message(
                "❌ あなたは大会にエントリーしていません。",
                ephemeral=True
            )
            return

        if user.id in self.bot.checked_in_users:

            await interaction.response.send_message(
                "⚠️ すでにチェックイン済みです。",
                ephemeral=True
            )
            return

        self.bot.checked_in_users.append(user.id)

        await interaction.response.send_message(
            "✅ チェックインが完了しました！",
            ephemeral=True
        )

        embed = discord.Embed(
            title="✅ チェックイン完了",
            description=f"{user.mention} さんがチェックインしました。",
            color=0x000000
        )

        await interaction.channel.send(embed=embed)
# =========================
# /can モーダル
# =========================

class TournamentModal(discord.ui.Modal, title="大会エントリー"):

    player_name = discord.ui.TextInput(
        label="大会で使用する名前",
        placeholder="例：プレイヤーA",
        required=True,
        max_length=32
    )

    friend_code = discord.ui.TextInput(
        label="フレンドコード",
        placeholder="例：0000-0000-0000",
        required=True,
        max_length=20
    )

    def __init__(self, bot_client):
        super().__init__()
        self.bot = bot_client

    async def on_submit(self, interaction: discord.Interaction):

        if interaction.user.id in self.bot.participants:

            await interaction.response.send_message(
                "❌ すでにエントリーしています。",
                ephemeral=True
            )
            return

        self.bot.participants.append(interaction.user.id)

        self.bot.player_details[interaction.user.id] = {
            "name": self.player_name.value,
            "friend_code": self.friend_code.value
        }

        embed = discord.Embed(
            title="✅ エントリー完了",
            color=0x000000
        )

        embed.add_field(
            name="大会名",
            value=self.player_name.value,
            inline=False
        )

        embed.add_field(
            name="フレンドコード",
            value=self.friend_code.value,
            inline=False
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


# =========================
# /can
# =========================

@app_commands.command(
    name="can",
    description="大会へエントリーします。"
)
async def can(self, interaction: discord.Interaction):

    await interaction.response.send_modal(
        TournamentModal(self)
    )
# =========================
# /drop
# =========================

class DropConfirmModal(discord.ui.Modal, title="大会辞退"):

    confirm = discord.ui.TextInput(
        label="辞退する場合は「はい」と入力してください",
        required=True,
        max_length=10
    )

    def __init__(self, bot_client):
        super().__init__()
        self.bot = bot_client

    async def on_submit(self, interaction: discord.Interaction):

        if self.confirm.value != "はい":

            await interaction.response.send_message(
                "❌ 「はい」と入力してください。",
                ephemeral=True
            )
            return

        user = interaction.user

        if user.id not in self.bot.participants:

            await interaction.response.send_message(
                "❌ あなたはエントリーしていません。",
                ephemeral=True
            )
            return

        self.bot.participants.remove(user.id)

        self.bot.player_details.pop(user.id, None)

        if user.id in self.bot.checked_in_users:
            self.bot.checked_in_users.remove(user.id)

        embed = discord.Embed(
            title="🚪 大会辞退",
            description=f"{user.mention} さんが大会を辞退しました。",
            color=0x000000
        )

        await interaction.response.send_message(
            "✅ 大会を辞退しました。",
            ephemeral=True
        )

        await interaction.channel.send(embed=embed)

        if hasattr(self.bot, "update_list_message"):
            await self.bot.update_list_message()


# =========================
# /drop
# =========================

@app_commands.command(
    name="drop",
    description="大会を辞退します。"
)
async def drop(self, interaction: discord.Interaction):

    await interaction.response.send_modal(
        DropConfirmModal(self)
    )
# =========================
# /list（管理者専用）
# =========================

@app_commands.command(
    name="list",
    description="参加者一覧を表示します。"
)
@app_commands.default_permissions(administrator=True)
async def list(self, interaction: discord.Interaction):

    if len(self.player_details) == 0:

        await interaction.response.send_message(
            "現在、参加者はいません。",
            ephemeral=True
        )
        return

    text = ""

    for i, player in enumerate(self.player_details.values(), start=1):

        text += (
            f"{i}. {player['name']}"
            f"（{player['friend_code']}）\n"
        )

    embed = discord.Embed(
        title="📋 参加者一覧",
        description=text,
        color=0x000000
    )

    embed.set_footer(
        text=f"参加者：{len(self.player_details)}人"
    )

    await interaction.response.send_message(embed=embed)


# =========================
# /checkinlist
# =========================

@app_commands.command(
    name="checkinlist",
    description="チェックイン済み一覧"
)
@app_commands.default_permissions(administrator=True)
async def checkinlist(self, interaction: discord.Interaction):

    if len(self.checked_in_users) == 0:

        await interaction.response.send_message(
            "まだ誰もチェックインしていません。",
            ephemeral=True
        )
        return

    text = ""

    for uid in self.checked_in_users:

        user = interaction.guild.get_member(uid)

        if user:
            text += f"・{user.display_name}\n"

    embed = discord.Embed(
        title="✅ チェックイン済み",
        description=text,
        color=0x000000
    )

    embed.set_footer(
        text=f"チェックイン：{len(self.checked_in_users)}人"
    )

    await interaction.response.send_message(embed=embed)


# =========================
# /notcheckin
# =========================

@app_commands.command(
    name="notcheckin",
    description="未チェックイン一覧"
)
@app_commands.default_permissions(administrator=True)
async def notcheckin(self, interaction: discord.Interaction):

    text = ""

    count = 0

    for uid in self.participants:

        if uid not in self.checked_in_users:

            user = interaction.guild.get_member(uid)

            if user:
                text += f"・{user.display_name}\n"
                count += 1

    if count == 0:
        text = "全員チェックイン済みです。"

    embed = discord.Embed(
        title="❌ 未チェックイン一覧",
        description=text,
        color=0x000000
    )

    embed.set_footer(
        text=f"未チェックイン：{count}人"
    )

    await interaction.response.send_message(embed=embed)


# =========================
# /help
# =========================

@app_commands.command(
    name="help",
    description="コマンド一覧"
)
async def help(self, interaction: discord.Interaction):

    embed = discord.Embed(
        title="📖 コマンド一覧",
        color=0x000000
    )

    embed.add_field(
        name="参加者",
        value=(
            "/can\n"
            "/drop"
        ),
        inline=False
    )

    embed.add_field(
        name="運営",
        value=(
            "/start\n"
            "/join\n"
            "/list\n"
            "/checkinlist\n"
            "/notcheckin"
        ),
        inline=False
    )

    await interaction.response.send_message(embed=embed)
# =========================
# /kick（管理者専用）
# =========================

@app_commands.command(
    name="kick",
    description="参加者を削除します。"
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(user="削除する参加者")
async def kick(
    self,
    interaction: discord.Interaction,
    user: discord.Member
):

    if user.id not in self.participants:

        await interaction.response.send_message(
            "❌ このユーザーはエントリーしていません。",
            ephemeral=True
        )
        return

    self.participants.remove(user.id)

    self.player_details.pop(user.id, None)

    if user.id in self.checked_in_users:
        self.checked_in_users.remove(user.id)

    embed = discord.Embed(
        title="🚫 参加者を削除しました",
        description=f"{user.mention} さんを参加者一覧から削除しました。",
        color=0x000000
    )

    await interaction.response.send_message(embed=embed)

    if hasattr(self, "update_list_message"):
        await self.update_list_message()


# =========================
# setup_hook
# =========================

async def setup_hook(self):

    self.tree.add_command(self.start)
    self.tree.add_command(self.can)
    self.tree.add_command(self.drop)
    self.tree.add_command(self.list)
    self.tree.add_command(self.help)
    self.tree.add_command(self.checkinlist)
    self.tree.add_command(self.notcheckin)
    self.tree.add_command(self.kick)

    self.add_view(CheckInButtonView(self))

    self.check_event_timer.start()

    await self.tree.sync()
client.run（'MTUyNzI5MTgyMTI0MjE5MTkwNQ.G_pLrJ.QyrHB6Du1L8GQmNnHHWqAANK0Ve1rkV0lpTnSY')
