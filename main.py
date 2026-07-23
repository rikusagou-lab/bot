"""
大会運営用 Discord Bot
--------------------------------
実装コマンド:
  /can        大会エントリー用モーダルを表示
                - 大会で使用したい名前 (必須)
                - フレンドコード (必須)
                - 進行役をやっていただけるか (任意・「はい」の場合のみ記入)
  /drop       エントリー取り消し用モーダルを表示
                - 「はい」と正確に入力した場合のみ取り消し成立
  /help       誰でも使える
                - コマンド一覧と説明を表示する(自分にだけ見える形で返信)
  /grant      管理者専用
                - 指定したユーザー(またはmember省略で全員)に、指定したロールを付与する
  /deprivation 管理者専用
                - 指定したユーザー(またはmember省略で全員)から、指定したロールを剥奪する
  /organizer  管理者専用
                - 指定したロールを「主催」に設定する(ロール自体への設定なので、
                  そのロールを持つ人数が変わっても主催の設定自体は変わらない)
  /start      管理者権限を持つ人だけが使える
                - 指定したロールを持つ人だけが /can /drop を使えるように設定する
                - 設定後、対象ロールを持たない人が /can /drop を実行すると
                  「権限がありません」と表示されフォームは開かない
  /list       管理者、または /organizer で設定した主催ロールを持つ人が使える
                - エントリー一覧を表示するチャンネルを指定する
                - 一覧は1つのメッセージにまとめて表示され、常に自動更新される
                - 進行役に「はい」と答えた人は名前の先頭に「進★」が付く
                  (例: 進★かぐや 0000-0000-0000)
                - /drop で取り消すと、その人の行が一覧から自動で消える
                - チェックイン状況も行末に ✅ / ❌ で表示される
  /checkin    管理者、または /organizer で設定した主催ロールを持つ人が使える
                - 大会開始日時とボタンを表示するチャンネルを指定する
                - 開始3時間前になると自動でチェックインボタン(緑)を投稿する
                - ボタンを押すとチェックイン完了。一覧の該当行に ✅ が付く
                - 開始10分前になっても未チェックインの人には、チェックイン
                  チャンネルでメンション付きリマインドを送る
                - 開始時刻になっても未チェックインの人は自動でエントリー
                  削除(/drop 相当)され、一覧からも消える
  /room       管理者、または主催ロールを持つ人が使える
                - チェックイン済みの人をランダムに部屋分けする(端数切り捨て)
                - 指定チャンネルに部屋ごとのスレッドを作成する
                  (スレッド名は「{ラウンド名} room{番号}」)
                - 各スレッドの最初のメッセージに、メンバー(名前・フレンド
                  コード)と最後に「進行役：」を投稿する
                - 指定チャンネルに組分け結果(進★付き、1行ずつ)を投稿する
  /facilitator 管理者、または主催ロールを持つ人が使える
                - 「進行役」として扱うロールを設定する(/table の使用権限に使う)
  /table      管理者・主催・進行役が使える(スレッド内で実行)
                - スレッドメンバー全員のスコアボード(初期値0)を作成する
                - ユーザーはスレッド内で数字だけを送信するとスコアが自動更新される
  /passcount  管理者、または主催ロールを持つ人が使える
                - 通過人数を設定する
  /result     管理者、または主催ロールを持つ人が使える
                - 最終リザルトを投稿するチャンネルを指定する
                - スレッド内でスコアボードの内容を貼り付けると、集計画像を
                  自動生成してスレッドに投稿し、✅❌のリアクションを付ける
                - ✅が6票入るか、30秒後に✅が❌より多ければ自動的に確定し、
                  指定チャンネルへ最終結果(画像+通過者リスト)を投稿する
                - 確定すると、通過者だけがエントリー一覧に残る
                  (続けて /room を実行すれば次ラウンドの組分けができる)

必要なライブラリ:
  pip install -U discord.py python-dotenv

事前準備:
  1. Discord Developer Portal( https://discord.com/developers/applications )で
     Botを作成し、TOKENを取得する
  2. Bot > Privileged Gateway Intents で
     「SERVER MEMBERS INTENT」「MESSAGE CONTENT INTENT」をONにする
     (前者はロール付与・メンバー情報取得、後者はスコア入力メッセージの読み取りに必要)
  3. OAuth2 > URL Generator で scope=bot,applications.commands、
     権限は最低限 "Manage Roles", "Create Public Threads", "Send Messages in Threads" を
     付けて、サーバーに招待する
  4. このファイルと同じ場所に .env ファイルを作り、以下を書く
        DISCORD_TOKEN=あなたのボットトークン
        GUILD_ID=あなたのサーバーID (スラッシュコマンドを即反映させるため。任意)
  5. リザルト画像で日本語を正しく表示するため、日本語対応フォント
     (例: Noto Sans JP)の .ttf ファイルをこのファイルと同じ場所に置き、
     ファイル名を NotoSansJP-Regular.ttf にする(なければ文字化けします)。
     ファイル名を変えたい場合は .env に RESULT_FONT_PATH=ファイル名 を追加する
"""

import os
import re
import io
import asyncio
import logging
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

JST = ZoneInfo("Asia/Tokyo")

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # 指定するとそのサーバーにだけ即座にコマンドが反映される
GUILD_OBJ = discord.Object(id=int(GUILD_ID)) if GUILD_ID else None
FONT_PATH = os.getenv("RESULT_FONT_PATH", "NotoSansJP-Regular.ttf")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tournament-bot")

# --------------------------------------------------------------------------
# Bot本体
# --------------------------------------------------------------------------
intents = discord.Intents.default()
intents.members = True  # ロール付与やメンバー情報取得に必要
intents.message_content = True  # スレッド内のスコア入力メッセージを読み取るために必要

bot = commands.Bot(command_prefix="!", intents=intents)

# エントリー情報を一時的に保存する簡易ストレージ(本番運用ではDB推奨)
# { user_id: {"name": str, "friend_code": str, "organizer": bool, "checked_in": bool} }
entries: dict[int, dict] = {}

# /can /drop の使用を許可するロール ( { guild_id: role_id } )
# 未設定(該当キーなし)の場合は誰でも使用可能
allowed_roles: dict[int, int] = {}

# エントリー一覧を表示するチャンネル ( { guild_id: channel_id } )
entry_list_channels: dict[int, int] = {}

# 一覧として編集し続けるメッセージのID ( { guild_id: message_id } )
entry_list_messages: dict[int, int] = {}

# チェックイン予定 ( { guild_id: {"target": datetime, "channel_id": int,
#   "posted": bool, "reminder_sent": bool, "deadline_processed": bool} } )
scheduled_checkins: dict[int, dict] = {}

# 「主催」として扱うロール ( { guild_id: role_id } )
# ロールIDで管理するため、そのロールを持つ人数が変わっても設定自体は変わらない
organizer_roles: dict[int, int] = {}

# 「進行役」として扱うロール ( { guild_id: role_id } )
facilitator_roles: dict[int, int] = {}

# スコアボード ( { thread_id: {"message_id": int, "scores": {user_id: int}, "names": {user_id: str}} } )
scoreboards: dict[int, dict] = {}

# 通過人数 ( { guild_id: int } )
passing_counts: dict[int, int] = {}

# 最終リザルトを投稿するチャンネル ( { guild_id: channel_id } )
result_channels: dict[int, int] = {}

# 現在リザルト確定の投票中のスレッド ( 二重トリガー防止用 )
voting_in_progress: set[int] = set()


def render_entry_list() -> str:
    """現在のエントリー一覧を1行1人の形式でテキスト化する"""
    if not entries:
        return "(現在エントリーはありません)"
    lines = []
    for data in entries.values():
        prefix = "進★" if data["organizer"] else ""
        status = "✅" if data.get("checked_in") else "❌"
        lines.append(f"{prefix}{data['name']} {data['friend_code']} {status}")
    return "\n".join(lines)


async def update_entry_list(guild: discord.Guild) -> None:
    """設定されていればエントリー一覧チャンネルのメッセージを作成・更新する"""
    channel_id = entry_list_channels.get(guild.id)
    if channel_id is None:
        return
    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    content = render_entry_list()
    message_id = entry_list_messages.get(guild.id)

    if message_id is not None:
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(content=content)
            return
        except discord.NotFound:
            pass  # メッセージが削除されていた場合は下で新規作成する
        except discord.Forbidden:
            log.warning(f"エントリー一覧チャンネル({channel_id})への編集権限がありません。")
            return

    try:
        message = await channel.send(content)
        entry_list_messages[guild.id] = message.id
    except discord.Forbidden:
        log.warning(f"エントリー一覧チャンネル({channel_id})への投稿権限がありません。")


def has_entry_permission(interaction: discord.Interaction) -> bool:
    """/can /drop を実行してよいユーザーか判定する"""
    role_id = allowed_roles.get(interaction.guild_id)
    if role_id is None:
        return True  # ロールが未設定なら全員使用可能
    if not isinstance(interaction.user, discord.Member):
        return False
    return any(r.id == role_id for r in interaction.user.roles)


def is_admin_or_organizer():
    """管理者、または設定された主催ロールを持つ人のみ実行を許可するチェック"""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        role_id = organizer_roles.get(interaction.guild_id)
        if role_id is None:
            return False
        return any(r.id == role_id for r in interaction.user.roles)

    return app_commands.check(predicate)


def is_admin_organizer_or_facilitator():
    """管理者、主催ロール、または進行役ロールを持つ人のみ実行を許可するチェック"""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        role_ids = {r.id for r in interaction.user.roles}
        organizer_role_id = organizer_roles.get(interaction.guild_id)
        if organizer_role_id is not None and organizer_role_id in role_ids:
            return True
        facilitator_role_id = facilitator_roles.get(interaction.guild_id)
        if facilitator_role_id is not None and facilitator_role_id in role_ids:
            return True
        return False

    return app_commands.check(predicate)


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    bot.add_view(CheckinView())  # Bot再起動後もボタンを使えるようにする
    if not checkin_scheduler.is_running():
        checkin_scheduler.start()
    try:
        if GUILD_OBJ:
            synced = await bot.tree.sync(guild=GUILD_OBJ)
        else:
            synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        log.exception(f"Command sync failed: {e}")


# --------------------------------------------------------------------------
# /can : エントリー用モーダル
# --------------------------------------------------------------------------
class EntryModal(discord.ui.Modal, title="大会エントリー"):
    tournament_name = discord.ui.TextInput(
        label="大会で使用したい名前",
        placeholder="例: たろう",
        required=True,
        max_length=32,
    )
    friend_code = discord.ui.TextInput(
        label="フレンドコード",
        placeholder="例: 1234-5678-9012",
        required=True,
        max_length=20,
    )
    organizer_flag = discord.ui.TextInput(
        label="進行役をやっていただけますか？",
        placeholder="やっていただける場合のみ「はい」と入力",
        required=False,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        is_organizer = self.organizer_flag.value.strip() == "はい"

        entries[interaction.user.id] = {
            "name": self.tournament_name.value.strip(),
            "friend_code": self.friend_code.value.strip(),
            "organizer": is_organizer,
            "checked_in": False,
        }

        embed = discord.Embed(title="エントリーを受け付けました", color=discord.Color.green())
        embed.add_field(name="大会で使用する名前", value=self.tournament_name.value, inline=False)
        embed.add_field(name="フレンドコード", value=self.friend_code.value, inline=False)
        embed.add_field(
            name="進行役",
            value="担当していただけます" if is_organizer else "担当なし",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await update_entry_list(interaction.guild)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception(error)
        await interaction.response.send_message(
            "エントリー処理中にエラーが発生しました。もう一度お試しください。", ephemeral=True
        )


@bot.tree.command(name="can", description="大会にエントリーします")
async def can(interaction: discord.Interaction):
    if not has_entry_permission(interaction):
        await interaction.response.send_message(
            "このコマンドを使用する権限がありません。", ephemeral=True
        )
        return
    await interaction.response.send_modal(EntryModal())


# --------------------------------------------------------------------------
# /drop : エントリー取り消し用モーダル
# --------------------------------------------------------------------------
class DropModal(discord.ui.Modal, title="エントリー取り消し"):
    confirm = discord.ui.TextInput(
        label="大会の登録を取り消しますか？",
        placeholder="取り消す場合は「はい」と入力してください",
        required=True,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm.value.strip() != "はい":
            await interaction.response.send_message(
                "「はい」以外の入力のため、取り消しは行われませんでした。",
                ephemeral=True,
            )
            return

        if interaction.user.id in entries:
            del entries[interaction.user.id]
            await interaction.response.send_message(
                "大会エントリーを取り消しました。", ephemeral=True
            )
            await update_entry_list(interaction.guild)
        else:
            await interaction.response.send_message(
                "エントリー情報が見つかりませんでした。", ephemeral=True
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception(error)
        await interaction.response.send_message(
            "取り消し処理中にエラーが発生しました。もう一度お試しください。", ephemeral=True
        )


@bot.tree.command(name="drop", description="大会のエントリーを取り消します")
async def drop(interaction: discord.Interaction):
    if not has_entry_permission(interaction):
        await interaction.response.send_message(
            "このコマンドを使用する権限がありません。", ephemeral=True
        )
        return
    await interaction.response.send_modal(DropModal())


# --------------------------------------------------------------------------
# /organizer : 指定したロールを「主催」に設定(管理者専用)
# 効果はロール自体に付与される。そのロールを持つ人数が変わっても設定は変わらない
# --------------------------------------------------------------------------
@bot.tree.command(name="organizer", description="【管理者用】指定したロールを「主催」に設定します")
@app_commands.describe(role="主催として扱うロール")
@app_commands.checks.has_permissions(administrator=True)
async def organizer(interaction: discord.Interaction, role: discord.Role):
    organizer_roles[interaction.guild_id] = role.id
    await interaction.response.send_message(
        f"「{role.name}」ロールを主催に設定しました。今後このロールを持つ人は "
        "/list /checkin などの主催用コマンドを使用できます。",
        ephemeral=True,
    )


@organizer.error
async def organizer_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "このコマンドは管理者権限を持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


# --------------------------------------------------------------------------
# /grant : 管理者専用、ユーザー(または全員)にロールを付与
# --------------------------------------------------------------------------
@bot.tree.command(name="grant", description="【管理者用】指定したユーザー(または全員)にロールを付与します")
@app_commands.describe(
    role="付与するロール",
    member="ロールを付与する対象ユーザー(指定しない場合は全員が対象になります)",
)
@app_commands.checks.has_permissions(administrator=True)
async def grant(interaction: discord.Interaction, role: discord.Role, member: discord.Member = None):
    # Bot自身がそのロールより上位にいないと付与できないので、事前にチェック
    if interaction.guild.me.top_role <= role:
        await interaction.response.send_message(
            f"Botのロール順位が「{role.name}」以下のため、このロールを付与できません。"
            "サーバー設定でBotのロールを上に移動してください。",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    targets = [member] if member is not None else [m for m in interaction.guild.members if not m.bot]

    success = 0
    failed = 0
    for target in targets:
        try:
            await target.add_roles(role, reason=f"{interaction.user} が /grant で付与")
            success += 1
        except discord.Forbidden:
            failed += 1

    if member is not None:
        await interaction.followup.send(
            f"{member.mention} に「{role.name}」ロールを付与しました。", ephemeral=True
        )
    else:
        await interaction.followup.send(
            f"全員(対象 {len(targets)}名)に「{role.name}」ロールを付与しました。"
            + (f"(失敗: {failed}名)" if failed else ""),
            ephemeral=True,
        )


@grant.error
async def grant_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "このコマンドは管理者権限を持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


# --------------------------------------------------------------------------
# /deprivation : 管理者専用、ユーザー(または全員)からロールを剥奪
# --------------------------------------------------------------------------
@bot.tree.command(name="deprivation", description="【管理者用】指定したユーザー(または全員)からロールを剥奪します")
@app_commands.describe(
    role="剥奪するロール",
    member="ロールを剥奪する対象ユーザー(指定しない場合は全員が対象になります)",
)
@app_commands.checks.has_permissions(administrator=True)
async def deprivation(interaction: discord.Interaction, role: discord.Role, member: discord.Member = None):
    # Bot自身がそのロールより上位にいないと剥奪できないので、事前にチェック
    if interaction.guild.me.top_role <= role:
        await interaction.response.send_message(
            f"Botのロール順位が「{role.name}」以下のため、このロールを剥奪できません。"
            "サーバー設定でBotのロールを上に移動してください。",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    targets = [member] if member is not None else [m for m in interaction.guild.members if not m.bot]

    success = 0
    failed = 0
    for target in targets:
        try:
            await target.remove_roles(role, reason=f"{interaction.user} が /deprivation で剥奪")
            success += 1
        except discord.Forbidden:
            failed += 1

    if member is not None:
        await interaction.followup.send(
            f"{member.mention} から「{role.name}」ロールを剥奪しました。", ephemeral=True
        )
    else:
        await interaction.followup.send(
            f"全員(対象 {len(targets)}名)から「{role.name}」ロールを剥奪しました。"
            + (f"(失敗: {failed}名)" if failed else ""),
            ephemeral=True,
        )


@deprivation.error
async def deprivation_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "このコマンドは管理者権限を持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


# --------------------------------------------------------------------------
# /start : 指定ロールのみ /can /drop を使えるように設定(管理者専用)
# --------------------------------------------------------------------------
@bot.tree.command(name="start", description="【管理者用】指定したロールのみ /can /drop を使えるように設定します")
@app_commands.describe(role="/can /drop の使用を許可するロール")
@app_commands.checks.has_permissions(administrator=True)
async def start(interaction: discord.Interaction, role: discord.Role):
    allowed_roles[interaction.guild_id] = role.id
    await interaction.response.send_message(
        f"設定しました。今後は「{role.name}」ロールを持つ人のみ /can /drop を使用できます。",
        ephemeral=True,
    )


@start.error
async def start_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "このコマンドは管理者権限を持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


# --------------------------------------------------------------------------
# /list : エントリー一覧を表示するチャンネルを指定(管理者専用)
# --------------------------------------------------------------------------
@bot.tree.command(name="list", description="【管理者・主催用】エントリー一覧を表示するチャンネルを指定します")
@app_commands.describe(channel="エントリー一覧を表示するチャンネル")
@is_admin_or_organizer()
async def list_(interaction: discord.Interaction, channel: discord.TextChannel):
    entry_list_channels[interaction.guild_id] = channel.id
    entry_list_messages.pop(interaction.guild_id, None)  # チャンネル変更時は新規メッセージを作り直す
    await interaction.response.send_message(
        f"設定しました。今後 {channel.mention} にエントリー一覧を表示します。",
        ephemeral=True,
    )
    await update_entry_list(interaction.guild)


@list_.error
async def list_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "このコマンドは管理者、または主催ロールを持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


# --------------------------------------------------------------------------
# /checkin : 開始時刻の3時間前にチェックインボタンを自動投稿(管理者・主催専用)
# --------------------------------------------------------------------------
class CheckinView(discord.ui.View):
    def __init__(self):
        # timeout=None + custom_id指定 で、Bot再起動後もボタンを使えるようにする
        super().__init__(timeout=None)

    @discord.ui.button(
        label="チェックイン",
        style=discord.ButtonStyle.green,
        custom_id="tournament_checkin_button",
        emoji="✅",
    )
    async def checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in entries:
            await interaction.response.send_message(
                "エントリー情報が見つかりません。先に /can でエントリーしてください。",
                ephemeral=True,
            )
            return

        entries[interaction.user.id]["checked_in"] = True
        await interaction.response.send_message("チェックインしました！", ephemeral=True)
        await update_entry_list(interaction.guild)


@bot.tree.command(name="checkin", description="【管理者・主催用】大会開始3時間前にチェックインボタンを表示します")
@app_commands.describe(
    date="大会開始日 (例: 2026-08-01)",
    time="大会開始時刻・日本時間 (例: 20:00)",
    channel="チェックインボタンを表示するチャンネル",
)
@is_admin_or_organizer()
async def checkin(interaction: discord.Interaction, date: str, time: str, channel: discord.TextChannel):
    try:
        target = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    except ValueError:
        await interaction.response.send_message(
            "日時の形式が正しくありません。例: date=2026-08-01 time=20:00", ephemeral=True
        )
        return

    checkin_time = target - timedelta(hours=3)
    if checkin_time <= datetime.now(JST):
        await interaction.response.send_message(
            "チェックイン開始時刻(大会開始の3時間前)がすでに過ぎています。日時を確認してください。",
            ephemeral=True,
        )
        return

    scheduled_checkins[interaction.guild_id] = {
        "target": target,
        "channel_id": channel.id,
        "posted": False,
        "reminder_sent": False,
        "deadline_processed": False,
    }
    await interaction.response.send_message(
        f"設定しました。大会開始 {target.strftime('%Y-%m-%d %H:%M')}(JST)の3時間前、"
        f"{checkin_time.strftime('%Y-%m-%d %H:%M')}(JST) に {channel.mention} へ"
        "チェックインボタンを表示します。",
        ephemeral=True,
    )


@checkin.error
async def checkin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "このコマンドは管理者、または主催ロールを持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


@tasks.loop(seconds=30)
async def checkin_scheduler():
    """30秒おきに予定を確認し、ボタン投稿・リマインド・締切処理を行う"""
    now = datetime.now(JST)
    for guild_id, info in list(scheduled_checkins.items()):
        guild = bot.get_guild(guild_id)
        if guild is None:
            continue
        channel = guild.get_channel(info["channel_id"])
        if channel is None:
            continue

        # 1. 開始3時間前 : チェックインボタンを投稿
        if not info["posted"] and now >= info["target"] - timedelta(hours=3):
            embed = discord.Embed(
                title="✅ チェックイン受付中",
                description=(
                    f"大会開始({info['target'].strftime('%Y-%m-%d %H:%M')} JST)まであと3時間です。\n"
                    "下のボタンを押してチェックインしてください。"
                ),
                color=discord.Color.green(),
            )
            try:
                await channel.send(embed=embed, view=CheckinView())
                info["posted"] = True
            except discord.Forbidden:
                log.warning(f"チェックインチャンネル({info['channel_id']})への投稿権限がありません。")

        # 2. 開始10分前 : 未チェックインの人にメンション付きリマインド
        if not info["reminder_sent"] and now >= info["target"] - timedelta(minutes=10):
            pending_ids = [
                uid for uid, data in entries.items() if not data.get("checked_in")
            ]
            if pending_ids:
                mentions = " ".join(f"<@{uid}>" for uid in pending_ids)
                try:
                    await channel.send(
                        f"{mentions}\n締切10分前になりました。まだチェックインが完了していません。"
                    )
                except discord.Forbidden:
                    log.warning(f"チェックインチャンネル({info['channel_id']})への投稿権限がありません。")
            info["reminder_sent"] = True

        # 3. 開始時刻 : 未チェックインの人を自動でエントリー削除
        if not info["deadline_processed"] and now >= info["target"]:
            removed_ids = [
                uid for uid, data in entries.items() if not data.get("checked_in")
            ]
            for uid in removed_ids:
                del entries[uid]

            if removed_ids:
                try:
                    await channel.send(
                        "締切になりました。未チェックインだった "
                        f"{len(removed_ids)}名 のエントリーを自動的に取り消しました。"
                    )
                except discord.Forbidden:
                    log.warning(f"チェックインチャンネル({info['channel_id']})への投稿権限がありません。")
                await update_entry_list(guild)

            info["deadline_processed"] = True


# --------------------------------------------------------------------------
# /room : チェックイン済みの参加者を部屋分けしてスレッドを作成(管理者・主催専用)
# --------------------------------------------------------------------------
@bot.tree.command(name="room", description="【管理者・主催用】チェックイン済みの参加者を部屋分けし、スレッドを作成します")
@app_commands.describe(
    round_name="スレッド名の元になる名前(例: Round1)",
    room_size="1部屋あたりの人数",
    thread_channel="スレッドを作成するチャンネル",
    announce_channel="組分け結果を投稿するチャンネル",
)
@is_admin_or_organizer()
async def room(
    interaction: discord.Interaction,
    round_name: str,
    room_size: app_commands.Range[int, 1, 50],
    thread_channel: discord.TextChannel,
    announce_channel: discord.TextChannel,
):
    await interaction.response.defer(ephemeral=True)

    # チェックイン済みの人だけを対象にする
    target = [(uid, data) for uid, data in entries.items() if data.get("checked_in")]

    if len(target) < room_size:
        await interaction.followup.send(
            f"チェックイン済みの人数({len(target)}名)が、1部屋の人数({room_size}名)に足りません。",
            ephemeral=True,
        )
        return

    random.shuffle(target)
    num_rooms = len(target) // room_size
    used = target[: num_rooms * room_size]
    leftover = target[num_rooms * room_size :]
    groups = [used[i * room_size : (i + 1) * room_size] for i in range(num_rooms)]

    summary_lines = [f"🏆 {round_name} 組分け結果"]
    created_threads = 0

    for i, group in enumerate(groups, start=1):
        room_label = f"room{i}"
        thread_name = f"{round_name} {room_label}"

        try:
            thread = await thread_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=1440,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"{thread_channel.mention} にスレッド作成権限がありません。処理を中断しました。",
                ephemeral=True,
            )
            return
        except Exception:
            log.exception(f"{thread_name} のスレッド作成に失敗しました")
            continue

        organizers_in_room = [data["name"] for _, data in group if data.get("organizer")]
        member_lines = [f"{data['name']}　{data['friend_code']}" for _, data in group]
        facilitator_line = "進行役：" + ("、".join(organizers_in_room) if organizers_in_room else "なし")
        thread_content = "\n".join(member_lines) + "\n\n" + facilitator_line

        try:
            await thread.send(thread_content)
        except discord.Forbidden:
            log.warning(f"{thread_name} への投稿権限がありません。")

        created_threads += 1

        summary_lines.append(f"\n{room_label}")
        for _, data in group:
            prefix = "進★" if data.get("organizer") else ""
            summary_lines.append(f"{prefix}{data['name']}")

    summary_text = "\n".join(summary_lines)
    try:
        # Discordのメッセージ文字数上限(2000)を考慮して分割送信
        for chunk_start in range(0, len(summary_text), 1900):
            await announce_channel.send(summary_text[chunk_start : chunk_start + 1900])
    except discord.Forbidden:
        await interaction.followup.send(
            f"{announce_channel.mention} への投稿権限がありません。", ephemeral=True
        )
        return

    leftover_note = ""
    if leftover:
        leftover_names = "、".join(data["name"] for _, data in leftover)
        leftover_note = f"\n切り捨てられた{len(leftover)}名: {leftover_names}"

    await interaction.followup.send(
        f"{created_threads}個のスレッドを作成し、{announce_channel.mention} に組分け結果を投稿しました。"
        + leftover_note,
        ephemeral=True,
    )


@room.error
async def room_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "このコマンドは管理者、または主催ロールを持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        if interaction.response.is_done():
            await interaction.followup.send("コマンド実行中にエラーが発生しました。", ephemeral=True)
        else:
            await interaction.response.send_message("コマンド実行中にエラーが発生しました。", ephemeral=True)


# --------------------------------------------------------------------------
# /facilitator : 「進行役」として扱うロールを設定(管理者・主催専用)
# --------------------------------------------------------------------------
@bot.tree.command(name="facilitator", description="【管理者・主催用】進行役として扱うロールを設定します")
@app_commands.describe(role="進行役として扱うロール")
@is_admin_or_organizer()
async def facilitator(interaction: discord.Interaction, role: discord.Role):
    facilitator_roles[interaction.guild_id] = role.id
    await interaction.response.send_message(
        f"「{role.name}」ロールを進行役に設定しました。今後このロールを持つ人は /table を使用できます。",
        ephemeral=True,
    )


@facilitator.error
async def facilitator_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "このコマンドは管理者、または主催ロールを持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


# --------------------------------------------------------------------------
# /passcount : 通過人数を設定(管理者・主催専用)
# --------------------------------------------------------------------------
@bot.tree.command(name="passcount", description="【管理者・主催用】通過人数を設定します")
@app_commands.describe(count="通過させる人数")
@is_admin_or_organizer()
async def passcount(interaction: discord.Interaction, count: app_commands.Range[int, 1, 100]):
    passing_counts[interaction.guild_id] = count
    await interaction.response.send_message(f"通過人数を {count}名 に設定しました。", ephemeral=True)


@passcount.error
async def passcount_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "このコマンドは管理者、または主催ロールを持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


# --------------------------------------------------------------------------
# /result : 最終リザルトを投稿するチャンネルを指定(管理者・主催専用)
# --------------------------------------------------------------------------
@bot.tree.command(name="result", description="【管理者・主催用】最終リザルトを投稿するチャンネルを指定します")
@app_commands.describe(channel="最終リザルトを投稿するチャンネル")
@is_admin_or_organizer()
async def result(interaction: discord.Interaction, channel: discord.TextChannel):
    result_channels[interaction.guild_id] = channel.id
    await interaction.response.send_message(
        f"設定しました。今後 {channel.mention} に最終リザルトを投稿します。", ephemeral=True
    )


@result.error
async def result_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "このコマンドは管理者、または主催ロールを持つ人のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


# --------------------------------------------------------------------------
# /table : スレッド内でスコアボードを作成(管理者・主催・進行役専用)
# --------------------------------------------------------------------------
def render_scoreboard(thread_id: int) -> str:
    board = scoreboards[thread_id]
    lines = ["数字だけを送信すると、あなたのスコアが自動で更新されます", ""]
    for uid, score in board["scores"].items():
        lines.append(f"{board['names'][uid]}　{score}")
    return "\n".join(lines)


@bot.tree.command(name="table", description="【管理者・主催・進行役用】スレッド内でスコアボードを作成します")
@is_admin_organizer_or_facilitator()
async def table(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message(
            "このコマンドはスレッド内で実行してください。", ephemeral=True
        )
        return

    thread = interaction.channel
    await interaction.response.defer(ephemeral=True)

    try:
        thread_members = await thread.fetch_members()
    except discord.HTTPException:
        thread_members = []

    scores: dict[int, int] = {}
    names: dict[int, str] = {}
    for tm in thread_members:
        member = interaction.guild.get_member(tm.id)
        if member is None or member.bot:
            continue
        scores[member.id] = 0
        names[member.id] = member.display_name

    scoreboards[thread.id] = {"message_id": None, "scores": scores, "names": names}
    content = render_scoreboard(thread.id)

    try:
        message = await thread.send(content)
        scoreboards[thread.id]["message_id"] = message.id
    except discord.Forbidden:
        await interaction.followup.send("このスレッドへの投稿権限がありません。", ephemeral=True)
        return

    await interaction.followup.send("スコアボードを作成しました。", ephemeral=True)


@table.error
async def table_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "このコマンドは管理者・主催・進行役のみ使用できます。", ephemeral=True
        )
    else:
        log.exception(error)
        await interaction.response.send_message(
            "コマンド実行中にエラーが発生しました。", ephemeral=True
        )


# --------------------------------------------------------------------------
# リザルト画像生成
# --------------------------------------------------------------------------
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        log.warning(
            f"フォント「{FONT_PATH}」が見つかりません。日本語が文字化けする場合があります。"
        )
        return ImageFont.load_default()


def render_result_image(ranked: list[tuple[str, int]], highlight_count: int, title: str) -> io.BytesIO:
    """ranked: [(名前, スコア), ...] (スコア降順)。上位 highlight_count 件を通過として色分けする。"""
    width = 560
    row_h = 52
    header_h = 80
    height = header_h + row_h * max(len(ranked), 1) + 20

    # 通過人数によって配色(見た目)を変える
    if highlight_count <= 1:
        accent = (230, 180, 40)  # 優勝者のみ: ゴールド
    elif highlight_count <= 3:
        accent = (200, 90, 60)  # 少人数通過: オレンジ寄り
    else:
        accent = (70, 150, 110)  # 通常: グリーン

    bg = (24, 24, 32)
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    title_font = _load_font(28)
    name_font = _load_font(22)
    score_font = _load_font(22)
    rank_font = _load_font(24)

    draw.text((20, 20), title, font=title_font, fill=(255, 255, 255))

    y = header_h
    for i, (name, score) in enumerate(ranked, start=1):
        advancing = i <= highlight_count
        row_color = accent if advancing else (48, 48, 58)
        draw.rectangle([10, y, width - 10, y + row_h - 6], fill=row_color)

        rank_color = (255, 255, 255) if advancing else (170, 170, 180)
        draw.text((22, y + 12), f"{i}", font=rank_font, fill=rank_color)
        draw.text((70, y + 12), name, font=name_font, fill=(255, 255, 255) if advancing else (200, 200, 210))
        score_text = str(score)
        draw.text((width - 90, y + 12), score_text, font=score_font, fill=(255, 255, 255))
        y += row_h

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# 「名前 スコア」形式の行にマッチする正規表現(全角/半角スペースどちらも許容)
_SCORE_LINE_RE = re.compile(r"^(.+?)[ \u3000]+(-?\d+)$")


def looks_like_scoreboard_paste(content: str) -> bool:
    """スコアボードを貼り付けたようなメッセージか(ゆるく)判定する"""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    unmatched = [line for line in lines if not _SCORE_LINE_RE.match(line)]
    matched_count = len(lines) - len(unmatched)
    return matched_count >= 2 and len(unmatched) <= 1


async def handle_result_trigger(message: discord.Message) -> None:
    """スコアボード貼り付けを検知したときの、画像生成〜投票開始までの処理"""
    thread = message.channel
    board = scoreboards.get(thread.id)
    if board is None or not board["scores"]:
        return
    if thread.id in voting_in_progress:
        return

    # 貼り付けテキストの値ではなく、Botが集計してきた実際のスコアを使う
    ranked = sorted(board["scores"].items(), key=lambda item: item[1], reverse=True)
    ranked_named = [(board["names"].get(uid, str(uid)), score) for uid, score in ranked]

    passcount = passing_counts.get(message.guild.id, len(ranked_named))
    passcount = min(passcount, len(ranked_named))

    image_buf = render_result_image(ranked_named, highlight_count=passcount, title="📊 集計結果(仮)")
    file = discord.File(fp=image_buf, filename="result.png")

    try:
        result_message = await thread.send(file=file)
        await result_message.add_reaction("✅")
        await result_message.add_reaction("❌")
    except discord.Forbidden:
        log.warning(f"スレッド({thread.id})への投稿・リアクション権限がありません。")
        return

    voting_in_progress.add(thread.id)
    bot.loop.create_task(watch_result_votes(result_message, ranked, passcount))


async def watch_result_votes(message: discord.Message, ranked_uids: list[tuple[int, int]], passcount: int) -> None:
    """✅が6票入るか、30秒経過時点で✅が❌より多ければ確定する"""
    try:
        start = datetime.now(JST)
        finalized = False

        while (datetime.now(JST) - start).total_seconds() < 30:
            await asyncio.sleep(2)
            try:
                fresh = await message.channel.fetch_message(message.id)
            except discord.NotFound:
                return
            yes = discord.utils.get(fresh.reactions, emoji="✅")
            yes_count = (yes.count - 1) if yes else 0  # Bot自身の1票を除く
            if yes_count >= 6:
                await finalize_result(message, ranked_uids, passcount)
                finalized = True
                break

        if not finalized:
            try:
                fresh = await message.channel.fetch_message(message.id)
            except discord.NotFound:
                return
            yes = discord.utils.get(fresh.reactions, emoji="✅")
            no = discord.utils.get(fresh.reactions, emoji="❌")
            yes_count = (yes.count - 1) if yes else 0
            no_count = (no.count - 1) if no else 0
            if yes_count > no_count:
                await finalize_result(message, ranked_uids, passcount)
            else:
                await message.channel.send("承認が多数に達しなかったため、この結果は確定しませんでした。")
    finally:
        voting_in_progress.discard(message.channel.id)


async def finalize_result(message: discord.Message, ranked_uids: list[tuple[int, int]], passcount: int) -> None:
    guild = message.guild
    channel_id = result_channels.get(guild.id)
    if channel_id is None:
        await message.channel.send(
            "⚠️ /result で結果投稿チャンネルが設定されていないため、最終結果を投稿できませんでした。"
        )
        return
    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    advancing = ranked_uids[:passcount]
    advancing_uids = {uid for uid, _ in advancing}

    ranked_named = [
        (entries.get(uid, {}).get("name") or f"<@{uid}>", score) for uid, score in ranked_uids
    ]
    image_buf = render_result_image(ranked_named, highlight_count=passcount, title=f"🏆 最終結果(通過 {passcount}名)")
    file = discord.File(fp=image_buf, filename="final_result.png")

    lines = ["通過者"]
    for uid, _ in advancing:
        data = entries.get(uid)
        name = data["name"] if data else f"<@{uid}>"
        prefix = "進★" if data and data.get("organizer") else ""
        lines.append(f"{prefix}{name}")

    try:
        await channel.send(content="\n".join(lines), file=file)
    except discord.Forbidden:
        await message.channel.send(f"⚠️ {channel.mention} への投稿権限がありません。")
        return

    # 通過者だけをエントリー一覧に残し、次ラウンドに向けてチェックイン状態をリセットする
    for uid in list(entries.keys()):
        if uid in advancing_uids:
            entries[uid]["checked_in"] = True
        else:
            del entries[uid]
    await update_entry_list(guild)

    await message.channel.send(
        f"✅ 確定しました。{channel.mention} に最終結果を投稿しました。"
        "通過者だけがエントリー一覧に残っているので、続けて /room で次の組分けができます。"
    )


@bot.event
async def on_message(message: discord.Message):
    if not message.author.bot and isinstance(message.channel, discord.Thread):
        board = scoreboards.get(message.channel.id)
        if board is not None:
            content = message.content.strip()

            # 数字だけのメッセージ : 自分のスコアとして記録
            if content.lstrip("-").isdigit():
                score = int(content)
                board["scores"][message.author.id] = score
                board["names"][message.author.id] = message.author.display_name

                if board["message_id"] is not None:
                    try:
                        board_message = await message.channel.fetch_message(board["message_id"])
                        await board_message.edit(content=render_scoreboard(message.channel.id))
                    except discord.NotFound:
                        pass

                try:
                    await message.add_reaction("✅")
                except discord.Forbidden:
                    pass

            # スコアボードらしき複数行の貼り付け : 集計画像を生成して投票開始
            elif looks_like_scoreboard_paste(content):
                await handle_result_trigger(message)

    # 他のprefixコマンドが動くように、必ず最後に呼び出す
    await bot.process_commands(message)


# --------------------------------------------------------------------------
# /help : コマンド一覧と説明を表示(誰でも使用可)
# --------------------------------------------------------------------------
@bot.tree.command(name="help", description="コマンド一覧と説明を表示します")
async def help_(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 コマンド一覧",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="/can",
        value="大会にエントリーします(名前・フレンドコードを入力。進行役希望なら「はい」)。",
        inline=False,
    )
    embed.add_field(
        name="/drop",
        value="大会のエントリーを取り消します(確認欄に「はい」と入力した場合のみ成立)。",
        inline=False,
    )
    embed.add_field(
        name="/help",
        value="このコマンド一覧を表示します。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /grant 【管理者用】",
        value="指定したユーザー(または全員)に、指定したロールを付与します。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /deprivation 【管理者用】",
        value="指定したユーザー(または全員)から、指定したロールを剥奪します。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /organizer 【管理者用】",
        value="指定したロールを「主催」に設定します(そのロールを持つ人数が変わっても設定は維持されます)。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /start 【管理者用】",
        value="指定したロールを持つ人だけが /can /drop を使えるように制限します。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /list 【管理者・主催用】",
        value="エントリー一覧を表示するチャンネルを指定します。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /checkin 【管理者・主催用】",
        value="大会開始日時とチェックインボタンを表示するチャンネルを指定します。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /room 【管理者・主催用】",
        value="チェックイン済みの人を部屋分けし、部屋ごとのスレッドを作成します。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /facilitator 【管理者・主催用】",
        value="「進行役」として扱うロールを設定します(/table の使用権限に使われます)。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /table 【管理者・主催・進行役用】",
        value="スレッド内でスコアボードを作成します。参加者は数字だけ送信するとスコアが自動更新されます。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /passcount 【管理者・主催用】",
        value="通過人数を設定します。",
        inline=False,
    )
    embed.add_field(
        name="🔒 /result 【管理者・主催用】",
        value=(
            "最終リザルトを投稿するチャンネルを指定します。"
            "スレッド内でスコアボードを貼り付けると集計画像が自動生成され、"
            "✅6票 or 30秒後に✅優勢で確定・投稿されます。"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --------------------------------------------------------------------------
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN が設定されていません。.env を確認してください。")
    bot.run(TOKEN)
