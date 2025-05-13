import os
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from telegram import ReplyKeyboardRemove
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    PicklePersistence
)
from dotenv import load_dotenv

# --- Configuração ---
def load_config():
    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("❌ TELEGRAM_TOKEN não encontrado no .env")
    service = os.getenv("RENDER_SERVICE_NAME", "telegram-gastos-bot")
    return token, service

def init_db(path='expenses.db'):
    conn = sqlite3.connect(path, check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id       INTEGER PRIMARY KEY,
            amount   REAL,
            category TEXT,
            person   TEXT,
            date     TEXT
        )
    ''')
    conn.commit()
    return conn

# --- Estados de conversa ---
AMOUNT, CATEGORY, PERSON, DATE = range(4)

# --- Handlers principais ---
def start(update, context):
    update.message.reply_text(
        "👋 Bem-vindo! Use /add para registrar gasto,\n"
        "/close_month para relatório,\n"
        "/clear_all para zerar tudo,\n"
        "/cleanup_old <dias> para apagar gastos mais antigos que X dias."
    )

def add(update, context):
    context.user_data.clear()
    update.message.reply_text("💰 Valor (ex: 50.00):", reply_markup=ReplyKeyboardRemove())
    return AMOUNT

def process_amount(update, context):
    try:
        amt = float(update.message.text)
        if amt <= 0: raise ValueError
        context.user_data['amount'] = amt
        update.message.reply_text("📂 Categoria (máx. 30 chars):")
        return CATEGORY
    except ValueError:
        update.message.reply_text("🔢 Digite número positivo válido.")
        return AMOUNT

def process_category(update, context):
    cat = update.message.text.strip()
    if len(cat) > 30:
        update.message.reply_text("📛 Categoria muito longa!")
        return CATEGORY
    context.user_data['category'] = cat
    update.message.reply_text("👤 Pessoa (máx. 20 chars):")
    return PERSON

def process_person(update, context):
    per = update.message.text.strip()
    if len(per) > 20:
        update.message.reply_text("📛 Nome muito longo!")
        return PERSON
    context.user_data['person'] = per
    update.message.reply_text("📅 Data DD/MM/AA (ex: 20/05/24):")
    return DATE

def process_date(update, context):
    date_str = update.message.text.strip()
    try:
        datetime.strptime(date_str, "%d/%m/%y")  # validação DD/MM/AA
        conn = context.bot_data['conn']
        conn.execute(
            "INSERT INTO expenses (amount, category, person, date) VALUES (?, ?, ?, ?)",
            (context.user_data['amount'],
             context.user_data['category'],
             context.user_data['person'],
             date_str)
        )
        conn.commit()
        update.message.reply_text("✅ Gasto registrado!")
        return ConversationHandler.END
    except ValueError:
        update.message.reply_text("📅 Use DD/MM/AA (ex: 20/05/24).")
        return DATE

def close_month(update, context):
    try:
        conn = context.bot_data['conn']
        df = pd.read_sql("SELECT * FROM expenses", conn)
        if df.empty:
            return update.message.reply_text("📭 Sem gastos neste mês!")
        # Preparação de datas
        df['date_obj'] = pd.to_datetime(df['date'], format="%d/%m/%y")
        df['date_fmt'] = df['date_obj'].dt.strftime("%d/%m/%y")
        total = df['amount'].sum()
        per_person = total / df['person'].nunique()
        balances = df.groupby('person')['amount'].sum() - per_person
        # Gráfico
        plt.figure(figsize=(10,6))
        df.groupby(['category','person'])['amount'].sum().unstack().plot(kind='bar')
        plt.title('Gastos por Categoria')
        plt.xticks(rotation=45)
        plt.tight_layout()
        chart_path = 'chart.png'
        plt.savefig(chart_path)
        plt.close()
        # Enviar e remover
        update.message.reply_photo(open(chart_path,'rb'))
        os.remove(chart_path)  # limpa imagem após envio
        # Texto
        lines = [
            f"📊 Relatório Mensal",
            f"Total: R${total:.2f}",
            f"Por pessoa: R${per_person:.2f}",
            "",
            "💵 Saldos:"
        ]
        for p,v in balances.items():
            status = 'deve pagar' if v>0 else 'deve receber'
            lines.append(f"{p}: R${v:.2f} ({status})")
        update.message.reply_text("\n".join(lines))
    except Exception as e:
        update.message.reply_text(f"⚠️ Erro no relatório: {e}")

# --- Manutenção ---
def clear_all(update, context):
    conn = context.bot_data['conn']
    conn.execute("DELETE FROM expenses")
    conn.commit()
    conn.execute("VACUUM")  # compacta arquivo SQLite
    update.message.reply_text("🗑️ Todos os gastos foram removidos.")

def cleanup_old(update, context):
    try:
        dias = int(context.args[0])
        cutoff = (datetime.now() - timedelta(days=dias)).strftime("%d/%m/%y")
        conn = context.bot_data['conn']
        conn.execute("DELETE FROM expenses WHERE date < ?", (cutoff,))
        conn.commit()
        conn.execute("VACUUM")
        update.message.reply_text(f"🗑️ Registros anteriores a {cutoff} removidos.")
    except (IndexError, ValueError):
        update.message.reply_text("Use: /cleanup_old <dias> (ex: /cleanup_old 90)")

def cancel(update, context):
    update.message.reply_text("❌ Operação cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def error_handler(update, context):
    update.message.reply_text("⚠️ Algo deu errado. Use /add para reiniciar.")

# --- Main ---
def main():
    token, service = load_config()
    persistence = PicklePersistence(
        filename='conv_data',
        store_bot_data=False  # desativa bot_data :contentReference[oaicite:5]{index=5}
    )
    updater = Updater(token, persistence=persistence, use_context=True)
    dp = updater.dispatcher
    dp.bot_data['conn'] = init_db()
    # ConversationHandler para /add
    conv = ConversationHandler(
        entry_points=[CommandHandler('add', add)],
        states={
            AMOUNT: [MessageHandler(Filters.text&~Filters.command,process_amount), CommandHandler('cancel',cancel)],
            CATEGORY: [MessageHandler(Filters.text&~Filters.command,process_category), CommandHandler('cancel',cancel)],
            PERSON: [MessageHandler(Filters.text&~Filters.command,process_person), CommandHandler('cancel',cancel)],
            DATE: [MessageHandler(Filters.text&~Filters.command,process_date), CommandHandler('cancel',cancel)],
        },
        fallbacks=[CommandHandler('cancel',cancel)],
        name="expenses_conversation", persistent=True
    )
    # /start, /close_month, manutenção
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('close_month', close_month))
    dp.add_handler(CommandHandler('clear_all', clear_all))
    dp.add_handler(CommandHandler('cleanup_old', cleanup_old))
    dp.add_handler(conv)
    dp.add_error_handler(error_handler)
    # Webhook no Render
    updater.start_webhook(
        listen='0.0.0.0',
        port=int(os.getenv('PORT','10000')),
        url_path=token,
        webhook_url=f"https://{service}.onrender.com/{token}"
    )
    updater.idle()

if __name__ == '__main__':
    main()
