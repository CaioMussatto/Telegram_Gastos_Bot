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
    ConversationHandler
)
from dotenv import load_dotenv

# Configurações iniciais

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
SERVICE_NAME = "telegram-gastos-bot-l4cb"

AMOUNT, CATEGORY, PERSON, DATE = range(4)


# Banco de Dados
def init_db():
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS expenses
                (id INTEGER PRIMARY KEY,
                 amount REAL,
                 category TEXT,
                 person TEXT,
                 date DATE)''')
    conn.commit()
    return conn


conn = init_db()


def close_month(update, context):
    try:
        # Buscar dados do banco
        df = pd.read_sql("SELECT * FROM expenses", conn)

        if df.empty:
            update.message.reply_text("📭 Nenhum gasto registrado este mês!")
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
                f"📊 Relatório Mensal\n"
                f"Total Gasto: R${total:.2f}\n"
                f"Valor por Pessoa: R${per_person:.2f}\n\n"
                "💵 Saldos:\n" +
                "\n".join([f"{p}: R${v:.2f} ({'deve pagar' if v > 0 else 'deve receber'})"
                           for p, v in saldos.items()])
        )

        # Enviar
        update.message.reply_photo(photo=open('chart.png', 'rb'))
        update.message.reply_text(report)

    except Exception as e:
        update.message.reply_text(f"⚠️ Erro ao gerar relatório: {str(e)}")

# ========== NOVAS FUNÇÕES DE RETRY ==========
def error_handler(update, context):
    """Lida com erros inesperados"""
    update.message.reply_text(
        "⚠️ Ops! Algo deu errado. Vamos começar de novo.\n"
        "Use /add para tentar novamente."
    )
    return ConversationHandler.END


def cancel(update, context):
    """Cancela a operação atual"""
    update.message.reply_text(
        "❌ Operação cancelada. Você pode começar de novo com /add",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ========== HANDLERS ATUALIZADOS ==========
def start(update, context):
    update.message.reply_text(
        "👋 Bem-vindo ao Bot de Gastos!\n"
        "📌 Comandos disponíveis:\n"
        "/add - Adicionar novo gasto\n"
        "/close_month - Fechar relatório mensal\n"
        "/help - Ajuda\n\n"
        "❓ Dica: Use /cancel a qualquer momento para recomeçar!"
    )


def add(update, context):
    """Inicia o fluxo de adição com limpeza de estado anterior"""
    context.user_data.clear()
    update.message.reply_text(
        "💰 Digite o valor gasto (ex: 50.00):\n"
        "❌ Use /cancel para desistir",
        reply_markup=ReplyKeyboardRemove()
    )
    return AMOUNT


def process_amount(update, context):
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError
        context.user_data['amount'] = amount
        update.message.reply_text(
            "📂 Categoria do gasto (ex: Alimentação, Transporte):\n"
            "❌ Use /cancel para recomeçar"
        )
        return CATEGORY
    except:
        update.message.reply_text(
            "🔢 Valor inválido! Digite apenas números positivos.\n"
            "Exemplo: 75.50\n"
            "Tente novamente:"
        )
        return AMOUNT  # Mantém no mesmo estado


def process_category(update, context):
    if len(update.message.text) > 30:
        update.message.reply_text(
            "📛 Categoria muito longa! Máximo 30 caracteres.\n"
            "Digite novamente:"
        )
        return CATEGORY

    context.user_data['category'] = update.message.text
    update.message.reply_text(
        "👤 Quem realizou o gasto? (ex: João, Maria):\n"
        "❌ Use /cancel para recomeçar"
    )
    return PERSON


def process_person(update, context):
    if len(update.message.text) > 20:
        update.message.reply_text(
            "📛 Nome muito longo! Máximo 20 caracteres.\n"
            "Digite novamente:"
        )
        return PERSON

    context.user_data['person'] = update.message.text
    update.message.reply_text(
        "📅 Data do gasto no formato AAAA-MM-DD (ex: 2024-05-20):\n"
        "❌ Use /cancel para recomeçar"
    )
    return DATE


def process_date(update, context):
    try:
        date_str = update.message.text
        datetime.strptime(date_str, "%d-%m-%y")  # Validação

        # Persistência
        c = conn.cursor()
        c.execute("INSERT INTO expenses VALUES (NULL,?,?,?,?)",
                  (context.user_data['amount'],
                   context.user_data['category'],
                   context.user_data['person'],
                   date_str))
        conn.commit()

        update.message.reply_text(
            "✅ Gasto registrado com sucesso!\n"
            "Você pode:\n"
            "- Adicionar outro com /add\n"
            "- Fechar o mês com /close_month"
        )
        return ConversationHandler.END

    except ValueError:
        update.message.reply_text(
            "📅 Formato de data inválido!\n"
            "Use exatamente DD-MM-YY (ex: 20-05-20)\n"
            "Tente novamente:"
        )
        return DATE  # Permanece no estado DATE para nova tentativa


# Resto do código (close_month e main) mantido igual ao anterior
# ... [Manter as funções close_month e main do código anterior]

def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    # Conversation Handler melhorado
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add)],
        states={
            AMOUNT: [
                MessageHandler(Filters.text, process_amount),
                CommandHandler('cancel', cancel)
            ],
            CATEGORY: [
                MessageHandler(Filters.text, process_category),
                CommandHandler('cancel', cancel)
            ],
            PERSON: [
                MessageHandler(Filters.text, process_person),
                CommandHandler('cancel', cancel)
            ],
            DATE: [
                MessageHandler(Filters.text, process_date),
                CommandHandler('cancel', cancel)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,  # Permite reiniciar o /add múltiplas vezes
        persistent=True,  # Mantém os dados entre reinícios do bot
        name="conversation"  # Necessário para persistent=True
    )

    # Registrar handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("close_month", close_month))
    dp.add_handler(conv_handler)
    #dp.add_error_handler(error_handler)

    # Configurar webhook
    updater.start_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get('PORT', 10000)),
        url_path=TOKEN,
        webhook_url=f"https://{SERVICE_NAME}.onrender.com/{TOKEN}"
    )

    updater.idle()


if __name__ == '__main__':
    main()