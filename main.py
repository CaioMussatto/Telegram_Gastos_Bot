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

# --- Configuração e inicialização ---
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
MODE, AMOUNT, CATEGORY, PERSON, DATE, LIST = range(6)

# --- Handlers de comandos ---
def start(update, context):
    update.message.reply_text(
        "👋 Olá! Eu sou seu Bot de Gastos.
Use /help para ver os comandos disponíveis."
    )

def help_command(update, context):
    update.message.reply_text(
        "📖 <b>Comandos disponíveis:</b>\n"
        "/start - Inicia o bot👋\n"
        "/add - Adicionar um gasto💰\n"
        "/close_month - Relatório mensal📊\n"
        "/clear_all - Limpar todos os gastos🗑️\n"
        "/cleanup_old <dias> - Apagar gastos antigos🕒\n"
        "/help - Este menu de ajudaℹ️",
        parse_mode='HTML'
    )

# --- Fluxo de adição de gastos ---
def add(update, context):
    context.user_data.clear()
    update.message.reply_text(
        "🛠️ Como deseja adicionar o gasto?\n"
        "1️⃣ Passo a passo\n"
        "2️⃣ Lista única (valor, categoria, pessoa, data)\n",
        reply_markup=ReplyKeyboardRemove()
    )
    return MODE


def process_mode(update, context):
    choice = update.message.text.strip()
    if choice == '1' or choice.startswith('1'):
        update.message.reply_text("💰 Digite o valor gasto (ex: 50.00):")
        return AMOUNT
    elif choice == '2' or choice.startswith('2'):
        update.message.reply_text(
            "✍️ Digite todos os dados separados por vírgula:\n"
            "Ex: 50.00, Alimentação, João, 20/05/24"
        )
        return LIST
    else:
        update.message.reply_text("❌ Opção inválida! Digite 1 ou 2:")
        return MODE


def process_amount(update, context):
    try:
        amt = float(update.message.text)
        if amt <= 0:
            raise ValueError
        context.user_data['amount'] = amt
        update.message.reply_text("📂 Categoria (máx. 30 chars):")
        return CATEGORY
    except ValueError:
        update.message.reply_text("🔢 Digite um número positivo válido.")
        return AMOUNT


def process_category(update, context):
    cat = update.message.text.strip()
    if len(cat) > 30:
        update.message.reply_text("📛 Categoria muito longa! Máx. 30 caracteres.")
        return CATEGORY
    context.user_data['category'] = cat
    update.message.reply_text("👤 Quem realizou o gasto? (máx. 20 chars):")
    return PERSON


def process_person(update, context):
    per = update.message.text.strip()
    if len(per) > 20:
        update.message.reply_text("📛 Nome muito longo! Máx. 20 caracteres.")
        return PERSON
    context.user_data['person'] = per
    update.message.reply_text("📅 Data DD/MM/AA (ex: 20/05/24):")
    return DATE


def process_date(update, context):
    date_str = update.message.text.strip()
    try:
        datetime.strptime(date_str, "%d/%m/%y")
        conn = context.bot_data['conn']
        conn.execute(
            "INSERT INTO expenses (amount, category, person, date) VALUES (?, ?, ?, ?)",
            (
                context.user_data['amount'],
                context.user_data['category'],
                context.user_data['person'],
                date_str
            )
        )
        conn.commit()
        update.message.reply_text("✅ Gasto registrado com sucesso!")
        return ConversationHandler.END
    except ValueError:
        update.message.reply_text("📅 Formato inválido! Use DD/MM/AA (ex: 20/05/24).")
        return DATE


def process_list(update, context):
    try:
        parts = [p.strip() for p in update.message.text.split(',')]
        amount, category, person, date_str = parts
        amt = float(amount)
        if amt <= 0:
            raise ValueError
        datetime.strptime(date_str, "%d/%m/%y")
        conn = context.bot_data['conn']
        conn.execute(
            "INSERT INTO expenses (amount, category, person, date) VALUES (?, ?, ?, ?)",
            (amt, category, person, date_str)
        )
        conn.commit()
        update.message.reply_text("✅ Gasto registrado via lista com sucesso!")
        return ConversationHandler.END
    except Exception:
        update.message.reply_text(
            "❌ Entrada inválida! Use: valor, categoria, pessoa, data (DD/MM/AA)"
        )
        return LIST

# --- Relatório e manutenção ---
def close_month(update, context):
    try:
        conn = context.bot_data['conn']
        df = pd.read_sql("SELECT * FROM expenses", conn)
        if df.empty:
            return update.message.reply_text("📭 Nenhum gasto registrado este mês!")
        df['date_obj'] = pd.to_datetime(df['date'], format="%d/%m/%y")
        total = df['amount'].sum()
        per = total / df['person'].nunique()
        balances = df.groupby('person')['amount'].sum() - per

        # Gráfico estilizado
        plt.figure(figsize=(10,6))
        ax = df.groupby(['category','person'])['amount'].sum().unstack().plot(
            kind='bar', edgecolor='black'
        )
        ax.set_title('📊 Gastos por Categoria', pad=15)
        ax.set_ylabel('Valor (R$)')
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        plt.xticks(rotation=45)
        plt.tight_layout()
        chart_path = 'chart.png'
        plt.savefig(chart_path)
        plt.close()

        update.message.reply_photo(open(chart_path,'rb'))
        os.remove(chart_path)

        text = [
            f"📊 <b>Relatório Mensal</b>",
            f"Total Gasto: R${total:.2f}",
            f"Por Pessoa: R${per:.2f}",
            "",
            "💵 <b>Saldos</b>:"
        ]
        for p, v in balances.items():
            status = 'deve pagar' if v>0 else 'deve receber'
            text.append(f"{p}: R${v:.2f} ({status})")

        update.message.reply_text("\n".join(text), parse_mode='HTML')
    except Exception as e:
        update.message.reply_text(f"⚠️ Erro no relatório: {e}")


def clear_all(update, context):
    conn = context.bot_data['conn']
    conn.execute("DELETE FROM expenses")
    conn.commit()
    conn.execute("VACUUM")
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
    except Exception:
        update.message.reply_text("Use: /cleanup_old <dias> (ex: /cleanup_old 90)")

# --- Cancelamento e erro ---
def cancel(update, context):
    update.message.reply_text("❌ Operação cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def error_handler(update, context):
    update.message.reply_text("⚠️ Algo deu errado. Use /add para reiniciar.")

# --- Função principal ---
def main():
    token, service = load_config()
    persistence = PicklePersistence('conv_data', store_bot_data=False)
    updater = Updater(token, persistence=persistence, use_context=True)
    dp = updater.dispatcher
    dp.bot_data['conn'] = init_db()

    conv = ConversationHandler(
        entry_points=[CommandHandler('add', add)],
        states={
            MODE: [MessageHandler(Filters.text & ~Filters.command, process_mode)],
            AMOUNT: [MessageHandler(Filters.text & ~Filters.command, process_amount), CommandHandler('cancel', cancel)],
            CATEGORY: [MessageHandler(Filters.text & ~Filters.command, process_category), CommandHandler('cancel', cancel)],
            PERSON: [MessageHandler(Filters.text & ~Filters.command, process_person), CommandHandler('cancel', cancel)],
            DATE: [MessageHandler(Filters.text & ~Filters.command, process_date), CommandHandler('cancel', cancel)],
            LIST: [MessageHandler(Filters.text & ~Filters.command, process_list), CommandHandler('cancel', cancel)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="expenses_conversation",
        persistent=True
    )

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('help', help_command))
    dp.add_handler(CommandHandler('close_month', close_month))
    dp.add_handler(CommandHandler('clear_all', clear_all))
    dp.add_handler(CommandHandler('cleanup_old', cleanup_old))
    dp.add_handler(conv)
    dp.add_error_handler(error_handler)

    updater.start_webhook(
        listen='0.0.0.0',
        port=int(os.getenv('PORT','10000')),
        url_path=token,
        webhook_url=f"https://{service}.onrender.com/{token}"
    )
    updater.idle()

if __name__ == '__main__':
    main()
