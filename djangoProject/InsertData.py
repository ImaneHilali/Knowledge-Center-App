import sqlite3

db_file = "C:\\Users\\emy7u\\PycharmProjects\\djangoProject\\db.sqlite3"

# Connect to the SQLite database
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

# Connect to the SQLite database
with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()

    # Create the files table if it doesn't exist
    cursor.execute('''CREATE TABLE IF NOT EXISTS files (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            path TEXT NOT NULL,
                            content TEXT NOT NULL,
                            embedding BLOB,
                            summary TEXT
                        )''')
    conn.commit()


# Close the database connection when done
conn.close()