import os
import sqlite3
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, ConversationHandler, MessageHandler, Filters
from dotenv import load_dotenv

# Configurações iniciais

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
SERVICE_NAME = "https://telegram-gastos-bot-l4cb"
AMOUNT, CATEGORY, PERSON, DATE = range(4)

# Banco de Dados
conn = sqlite3.connect('expenses.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS expenses
             (id INTEGER PRIMARY KEY,
              amount REAL,
              category TEXT,
              person TEXT,
              date DATE)''')
conn.commit()


# ========== HANDLERS ==========
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Olá! Sou seu bot de controle de gastos.\n"
        "Comandos:\n"
        "/add - Adicionar gasto\n"
        "/close_month - Fechar mês\n"
        "/help - Ajuda"
    )


def add(update: Update, context: CallbackContext):
    update.message.reply_text("💰 Digite o valor gasto:")
    return AMOUNT


def process_amount(update: Update, context: CallbackContext):
    try:
        context.user_data['amount'] = float(update.message.text)
        update.message.reply_text("📂 Categoria (ex: Alimentação):")
        return CATEGORY
    except ValueError:
        update.message.reply_text("❌ Valor inválido! Use números.")
        return AMOUNT


def process_category(update: Update, context: CallbackContext):
    context.user_data['category'] = update.message.text
    update.message.reply_text("👤 Quem gastou?")
    return PERSON


def process_person(update: Update, context: CallbackContext):
    context.user_data['person'] = update.message.text
    update.message.reply_text("📅 Data (AAAA-MM-DD):")
    return DATE


def process_date(update: Update, context: CallbackContext):
    try:
        date = datetime.strptime(update.message.text, "%Y-%m-%d").date()

        c.execute("INSERT INTO expenses (amount, category, person, date) VALUES (?,?,?,?)",
                  (context.user_data['amount'],
                   context.user_data['category'],
                   context.user_data['person'],
                   date))
        conn.commit()

        update.message.reply_text("✅ Gasto registrado!")
        return ConversationHandler.END
    except Exception as e:
        update.message.reply_text(f"❌ Erro: {str(e)}")
        return DATE


def close_month(update: Update, context: CallbackContext):
    try:
        df = pd.read_sql("SELECT * FROM expenses", conn)

        if df.empty:
            update.message.reply_text("📭 Nenhum gasto este mês!")
            return

        # Cálculos
        total = df['amount'].sum()
        per_person = total / 2
        saldos = df.groupby('person')['amount'].sum() - per_person

        # Gráfico
        plt.figure(figsize=(10, 6))
        df.groupby(['category', 'person'])['amount'].sum().unstack().plot(kind='bar')
        plt.title('Gastos por Categoria')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig('chart.png')

        # Relatório
        report = (
                f"📊 **Relatório Mensal**\n"
                f"Total: R${total:.2f}\n"
                f"Valor por pessoa: R${per_person:.2f}\n\n"
                "**Saldos:**\n" +
                "\n".join([f"{p}: R${v:.2f} ({'deve' if v > 0 else 'recebe'} R${abs(v):.2f})"
                           for p, v in saldos.items()])
        )

        # Enviar
        update.message.reply_photo(open('chart.png', 'rb'))
        update.message.reply_text(report, parse_mode='Markdown')

    except Exception as e:
        update.message.reply_text(f"⚠️ Erro: {str(e)}")


# ========== CONFIG SERVIDOR ==========
def main():
    updater = Updater(TOKEN, use_context=True)

    # Configurar Webhook (OBRIGATÓRIO PARA RENDER)
    PORT = int(os.environ.get('PORT', 10000))
    webhook_url = f"https://{SERVICE_NAME}.onrender.com/{TOKEN}"

    updater.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=webhook_url
    )

    # Handlers
    dp = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_amount)],
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_category)],
            PERSON: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_person)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_date)]
        },
        fallbacks=[]
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("close_month", close_month))
    dp.add_handler(conv_handler)

    updater.idle()


if __name__ == '__main__':
    main()