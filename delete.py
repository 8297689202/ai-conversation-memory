import sqlite3

DB_NAME = "story_conversations.db"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Delete last 5 rows from messages table
cursor.execute('''
    DELETE FROM messages 
    WHERE id IN (
        SELECT id FROM messages 
        ORDER BY timestamp DESC 
        LIMIT 6
    )
''')

print(f"Deleted {cursor.rowcount} rows")
conn.commit()
conn.close()