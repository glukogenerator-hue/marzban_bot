import sqlite3
import sys

def main():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    # Получаем список таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print('Таблицы в базе данных:')
    for table in tables:
        print(f'  - {table[0]}')
    
    # Смотрим структуру таблицы transactions
    cursor.execute("PRAGMA table_info(transactions);")
    columns = cursor.fetchall()
    print('\nСтруктура таблицы transactions:')
    for col in columns:
        print(f'  {col[1]} ({col[2]})')
    
    # Выбираем все транзакции с описанием, содержащим 'добровольная благодарность'
    cursor.execute("SELECT id, order_id, amount, description, status, created_at FROM transactions WHERE description LIKE '%добровольная благодарность%' ORDER BY created_at DESC LIMIT 10;")
    transactions = cursor.fetchall()
    print('\nТранзакции с описанием "добровольная благодарность":')
    for t in transactions:
        print(f'  ID: {t[0]}, Order: {t[1]}, Amount: {t[2]}, Status: {t[4]}, Date: {t[5]}')
        print(f'    Description: {t[3]}')
    
    # Ищем транзакции с order_id, содержащим '32' или номером 32
    cursor.execute("SELECT id, order_id, amount, description, status, created_at FROM transactions WHERE order_id LIKE '%32%' OR id = 32;")
    transactions32 = cursor.fetchall()
    print('\nТранзакции, связанные с "32":')
    for t in transactions32:
        print(f'  ID: {t[0]}, Order: {t[1]}, Amount: {t[2]}, Status: {t[4]}, Date: {t[5]}')
        print(f'    Description: {t[3]}')
    
    # Проверяем, есть ли транзакция с ID 32
    cursor.execute("SELECT id, order_id, amount, description, status, created_at FROM transactions WHERE id = 32;")
    transaction_id_32 = cursor.fetchone()
    if transaction_id_32:
        print('\nТранзакция с ID 32:')
        print(f'  ID: {transaction_id_32[0]}, Order: {transaction_id_32[1]}, Amount: {transaction_id_32[2]}, Status: {transaction_id_32[4]}, Date: {transaction_id_32[5]}')
        print(f'    Description: {transaction_id_32[3]}')
    
    conn.close()

if __name__ == '__main__':
    main()