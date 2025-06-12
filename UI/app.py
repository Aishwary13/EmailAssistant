from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

CATEGORIES = [
    "Announcements", "Feedback", "non-complaince", "System Generated Mails",
    "Others", "Events", "Meetings", "Updates", "Marketing"
]

def get_emails_by_category(category):
    with sqlite3.connect('C:\\Users\\aracentwindowsvm\\Desktop\\Emailtool\\EmailAssistant\\emails.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ID, sender, subject FROM emails WHERE category = ?", (category,))
        return cursor.fetchall()

def get_email_by_id(email_id):
    with sqlite3.connect('C:\\Users\\aracentwindowsvm\\Desktop\\Emailtool\\EmailAssistant\\emails.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM emails WHERE ID = ?", (email_id,))
        return cursor.fetchone()

@app.route('/')
def index():
    selected_category = request.args.get('category', CATEGORIES[0])
    selected_email_id = request.args.get('email_id')
    
    emails = get_emails_by_category(selected_category)
    email_detail = get_email_by_id(selected_email_id) if selected_email_id else None
    
    return render_template('index.html',
                           categories=CATEGORIES,
                           selected_category=selected_category,
                           emails=emails,
                           selected_email=email_detail)
    
if __name__ == '__main__':
    app.run(debug=True)
