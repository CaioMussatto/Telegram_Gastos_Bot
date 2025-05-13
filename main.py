import os
import sqlite3
from datetime import datetime
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

# Carrega config do .env
def load_config():
    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("❌ TELEGRAM_TOKEN não encontrado no .env")
    service = os.getenv("RENDER_SERVICE_NAME", "telegram-gastos-bot")
    return token, service

# Inicializa banco SQLite
def init_db(db_path='expenses.db'):
    conn = sqlite3.connect(db_path, check_same_thread=False)
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

# Estados da conversa
AMOUNT, CATEGORY, PERSON, DATE = range(4)

def start(update, context):
    update.message.reply_text(
        "👋 Bem-vindo ao Bot de Gastos!\n"
        "Use /add para adicionar um gasto ou /close_month para relatório."
    )

def add(update, context):
    context.user_data.clear()
    update.message.reply_text(
        "💰 Digite o valor gasto (ex: 50.00):",
        reply_markup=ReplyKeyboardRemove()
    )
    return AMOUNT

def process_amount(update, context):
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError
        context.user_data['amount'] = amount
        update.message.reply_text("📂 Informe a categoria (máx. 30 caracteres):")
        return CATEGORY
    except ValueError:
        update.message.reply_text("🔢 Valor inválido! Digite um número positivo.")
        return AMOUNT

def process_category(update, context):
    cat = update.message.text.strip()
    if len(cat) > 30:
        update.message.reply_text("📛 Categoria muito longa! Máximo 30 caracteres.")
        return CATEGORY
    context.user_data['category'] = cat
    update.message.reply_text("👤 Quem realizou o gasto? (máx. 20 caracteres):")
    return PERSON

def process_person(update, context):
    person = update.message.text.strip()
    if len(person) > 20:
        update.message.reply_text("📛 Nome muito longo! Máximo 20 caracteres.")
        return PERSON
    context.user_data['person'] = person
    update.message.reply_text("📅 Data no formato DD/MM/AA (ex: 20/05/24):")
    return DATE

def process_date(update, context):
    date_str = update.message.text.strip()
    try:
        # Valida DD/MM/AA
        date_obj = datetime.strptime(date_str, "%d/%m/%y")  # aceita DD/MM/AA :contentReference[oaicite:2]{index=2}
        conn = context.bot_data['conn']
        c = conn.cursor()
        c.execute(
            "INSERT INTO expenses (amount, category, person, date) VALUES (?, ?, ?, ?)",
            (
                context.user_data['amount'],
                context.user_data['category'],
                context.user_data['person'],
                date_str  # mantém DD/MM/AA no DB
            )
        )
        conn.commit()
        update.message.reply_text("✅ Gasto registrado com sucesso!")
        return ConversationHandler.END
    except ValueError:
        update.message.reply_text(
            "📅 Formato inválido! Use DD/MM/AA (ex: 20/05/24). Tente novamente:"
        )
        return DATE

def close_month(update, context):
    try:
        df = pd.read_sql("SELECT * FROM expenses", context.bot_data['conn'])
        if df.empty:
            update.message.reply_text("📭 Nenhum gasto registrado este mês!")
            return
        # Converte para datetime caso venha em ISO
        df['date_obj'] = pd.to_datetime(df['date'], format="%d/%m/%y", errors='coerce')
        # Reexibe no formato DD/MM/AA
        df['date_fmt'] = df['date_obj'].dt.strftime("%d/%m/%y")  # mantém DD/MM/AA :contentReference[oaicite:3]{index=3}

        total = df['amount'].sum()
        per_person = total / df['person'].nunique()
        balances = df.groupby('person')['amount'].sum() - per_person

        # Gera gráfico
        plt.figure(figsize=(10, 6))
        df.groupby(['category', 'person'])['amount'].sum().unstack().plot(kind='bar')
        plt.title('Gastos por Categoria')
        plt.xticks(rotation=45)
        plt.tight_layout()
        chart_path = 'chart.png'
        plt.savefig(chart_path)
        plt.close()

        # Monta relatório
        lines = [
            f"📊 Relatório Mensal",
            f"Total Gasto: R${total:.2f}",
            f"Valor por Pessoa: R${per_person:.2f}",
            "",
            "💵 Saldos:"
        ]
        for p, v in balances.items():
            status = 'deve pagar' if v > 0 else 'deve receber'
            lines.append(f"{p}: R${v:.2f} ({status})")

        update.message.reply_photo(photo=open(chart_path, 'rb'))
        update.message.reply_text("\n".join(lines))
    except Exception as e:
        update.message.reply_text(f"⚠️ Erro ao gerar relatório: {e}")

def cancel(update, context):
    update.message.reply_text(
        "❌ Operação cancelada.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def error_handler(update, context):
    update.message.reply_text(
        "⚠️ Ops! Algo deu errado. Use /add para tentar novamente."
    )
    return ConversationHandler.END

def main():
    token, service = load_config()
    persistence = PicklePersistence(filename='conversationbot_data')
    updater = Updater(token, persistence=persistence, use_context=True)
    dp = updater.dispatcher

    # Conexão SQLite em bot_data
    dp.bot_data['conn'] = init_db()

    # ConversationHandler
    conv = ConversationHandler(
        entry_points=[CommandHandler('add', add)],
        states={
            AMOUNT: [MessageHandler(Filters.text & ~Filters.command, process_amount), CommandHandler('cancel', cancel)],
            CATEGORY: [MessageHandler(Filters.text & ~Filters.command, process_category), CommandHandler('cancel', cancel)],
            PERSON: [MessageHandler(Filters.text & ~Filters.command, process_person), CommandHandler('cancel', cancel)],
            DATE: [MessageHandler(Filters.text & ~Filters.command, process_date), CommandHandler('cancel', cancel)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="expenses_conversation",
        persistent=True
    )

    # Registra handlers
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('close_month', close_month))
    dp.add_handler(conv)
    dp.add_error_handler(error_handler)

    # Webhook no Render
    updater.start_webhook(
        listen='0.0.0.0',
        port=int(os.environ.get('PORT', '10000')),
        url_path=token,
        webhook_url=f"https://{service}.onrender.com/{token}"
    )
    updater.idle()

if __name__ == '__main__':
    main()
