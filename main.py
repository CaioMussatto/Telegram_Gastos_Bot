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

# Estados da conversa
AMOUNT, CATEGORY, PERSON, DATE = range(4)

# Criar banco de dados se não existir
conn = sqlite3.connect('database/expenses.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS expenses
             (id INTEGER PRIMARY KEY,
              amount REAL,
              category TEXT,
              person TEXT,
              date DATE)''')
conn.commit()


# ========== HANDLERS PRINCIPAIS ==========
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Olá! Sou seu bot de controle de gastos.\n"
        "Comandos disponíveis:\n"
        "/add - Adicionar novo gasto\n"
        "/close_month - Fechar o mês\n"
        "/help - Ajuda"
    )


def add(update: Update, context: CallbackContext):
    update.message.reply_text("💰 Por favor, digite o valor gasto:")
    return AMOUNT


def process_amount(update: Update, context: CallbackContext):
    try:
        amount = float(update.message.text)
        context.user_data['amount'] = amount
        update.message.reply_text("📂 Digite a categoria (ex: Alimentação, Transporte):")
        return CATEGORY
    except ValueError:
        update.message.reply_text("❌ Valor inválido! Digite apenas números.")
        return AMOUNT


def process_category(update: Update, context: CallbackContext):
    context.user_data['category'] = update.message.text
    update.message.reply_text("👤 Quem gastou? (Digite o nome):")
    return PERSON


def process_person(update: Update, context: CallbackContext):
    context.user_data['person'] = update.message.text
    update.message.reply_text("📅 Data do gasto (Formato AAAA-MM-DD):")
    return DATE


def process_date(update: Update, context: CallbackContext):
    try:
        date_str = update.message.text
        datetime.strptime(date_str, '%Y-%m-%d')  # Validar formato

        # Salvar no banco de dados
        c.execute("INSERT INTO expenses (amount, category, person, date) VALUES (?, ?, ?, ?)",
                  (context.user_data['amount'],
                   context.user_data['category'],
                   context.user_data['person'],
                   date_str))
        conn.commit()

        update.message.reply_text("✅ Gasto adicionado com sucesso!")
        return ConversationHandler.END
    except Exception as e:
        update.message.reply_text(f"❌ Data inválida! Erro: {str(e)}")
        return DATE


def close_month(update: Update, context: CallbackContext):
    try:
        # Ler dados do banco
        df = pd.read_sql_query("SELECT * FROM expenses", conn)

        if df.empty:
            update.message.reply_text("📭 Nenhum gasto registrado este mês!")
            return

        # Calcular totais
        total = df['amount'].sum()
        per_person = total / 2

        # Calcular diferenças
        people = df.groupby('person')['amount'].sum().reset_index()
        people['diferença'] = people['amount'] - per_person

        # Gerar gráfico de categorias
        plt.figure(figsize=(10, 6))
        df.groupby(['category', 'person'])['amount'].sum().unstack().plot(kind='bar')
        plt.title('Gastos por Categoria e Pessoa')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig('charts/categories.png')

        # Criar relatório
        report = f"📊 **Relatório Mensal**\n\n"
        report += f"Total gasto: R${total:.2f}\n"
        report += f"Valor por pessoa: R${per_person:.2f}\n\n"
        report += "**Saldos:**\n" + "\n".join(
            [f"{row['person']}: R${row['diferença']:.2f} ({'deve receber' if row['diferença'] < 0 else 'deve pagar'})"
             for _, row in people.iterrows()]
        )

        # Enviar resultados
        update.message.reply_photo(open('charts/categories.png', 'rb'))
        update.message.reply_text(report, parse_mode='Markdown')

    except Exception as e:
        update.message.reply_text(f"⚠️ Erro ao gerar relatório: {str(e)}")


def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END


# ========== CONFIGURAÇÃO DO BOT ==========
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add)],
        states={
            AMOUNT: [MessageHandler(Filters.text & ~Filters.command, process_amount)],
            CATEGORY: [MessageHandler(Filters.text & ~Filters.command, process_category)],
            PERSON: [MessageHandler(Filters.text & ~Filters.command, process_person)],
            DATE: [MessageHandler(Filters.text & ~Filters.command, process_date)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("close_month", close_month))
    dp.add_handler(conv_handler)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()