from flask import Flask, render_template, request, session, redirect, url_for, Response
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_connection
import re
import os


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        fullname TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses(
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        date TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS budgets(
        user_id INTEGER PRIMARY KEY,
        amount REAL NOT NULL
    )
    """)

    conn.commit()
    conn.close()


app = Flask(__name__)


init_db()


app.secret_key = os.environ.get(
    "SECRET_KEY",
    "fintrack_secret_key"
)

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/logout")
def logout():

    session.pop("user_id", None)

    return redirect(url_for("login"))



@app.route("/delete/<int:id>")
def delete_expense(id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM expenses WHERE id=%s AND user_id=%s",
        (id, session["user_id"])
    )

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))



@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_expense(id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":

       
        title = request.form["title"]

        try:
            amount = float(request.form["amount"])
        except ValueError:
            return "Please enter a valid amount"

        if amount <= 0:
            return "Amount must be greater than 0"
        
        category = request.form["category"]
        date = request.form["date"]

        cursor.execute("""
        UPDATE expenses
        SET title=%s, amount=%s, category=%s, date=%s
        WHERE id=%s AND user_id=%s
        """, (
            title,
            amount,
            category,
            date,
            id,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    cursor.execute(
        "SELECT * FROM expenses WHERE id=%s AND user_id=%s",
        (id, session["user_id"])
    )

    expense = cursor.fetchone()

    if expense is None:
        conn.close()
        return redirect(url_for("dashboard"))

    conn.close()

    return render_template(
        "edit_expense.html",
        expense=expense
    )



@app.route("/add_expense", methods=["GET", "POST"])
def add_expense():

    if "user_id" not in session:
        return redirect(url_for("login"))


    if request.method == "POST":

        title = request.form["title"]

        try:
            amount = float(request.form["amount"])
        except ValueError:
            return "Please enter a valid amount"

        if amount <= 0:
            return "Amount must be greater than 0"
        
        category = request.form["category"]
        date = request.form["date"]

        user_id = session["user_id"]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO expenses(user_id,title,amount,category,date)
        VALUES(%s,%s,%s,%s,%s)
        """, (user_id, title, amount, category, date))

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("add_expense.html")



@app.route("/set_budget", methods=["GET", "POST"])
def set_budget():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":

        try:
            amount = float(request.form["amount"])
        except ValueError:
            return "Please enter a valid amount"

        if amount <= 0:
            return "Amount must be greater than 0"

        cursor.execute("""
            INSERT INTO budgets(user_id, amount)
            VALUES(%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET amount = EXCLUDED.amount
            """, (user_id, amount)
        )
        
        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    cursor.execute(
        "SELECT amount FROM budgets WHERE user_id=%s",
        (user_id,)
    )

    budget_data = cursor.fetchone()

    budget = budget_data[0] if budget_data else 0

    conn.close()

    return render_template(
        "set_budget.html",
        budget=budget
    )





@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip()
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )

        user = cursor.fetchone()

        conn.close()

        if user and check_password_hash(user[3], password):
            session["user_id"] = user[0]
            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid Email or Password"
        )

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    search = request.args.get("search", "")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE id=%s",
        (user_id,)
    )

    user = cursor.fetchone()

    cursor.execute(
        "SELECT amount FROM budgets WHERE user_id=%s",
        (user_id,)
    )

    budget_data = cursor.fetchone()

    cursor.execute(
    "SELECT * FROM expenses WHERE user_id=%s",
    (user_id,)
    )

    all_expenses = cursor.fetchall()

    

    cursor.execute("""
        SELECT * FROM expenses
        WHERE user_id=%s AND
        (
            title LIKE %s
            OR category LIKE %s
        )
        """,
        (
            user_id,
            f"%{search}%",
            f"%{search}%"
        ))

    expenses = cursor.fetchall()

    categories = {}

    for expense in all_expenses:

        category = expense[4]
        amount = expense[3]

        categories[category] = categories.get(category, 0) + amount

    category_labels = list(categories.keys())
    category_values = list(categories.values())

    total = sum(expense[3] for expense in all_expenses)

    if budget_data:
        budget = budget_data[0]
    else:
        budget = 0

    remaining = budget - total

    if remaining >= 0:
        status = "Within Budget ✅"
    else:
        status = "Budget Exceeded ⚠️"

    conn.close()

    return render_template(
        "dashboard.html",
        name=user[1],
        expenses=expenses,
        total=total,
        categories=categories,
        category_labels=category_labels,
        category_values=category_values,
        budget=budget,
        remaining=remaining,
        status=status,
        search=search
    )


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        fullname = request.form["fullname"].strip()
        if len(fullname) < 3:
            return "Name must be at least 3 characters"
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            return "Passwords do not match"

        

        email_pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'

        if not re.match(email_pattern, email):
            return "Invalid Email Format"

        password_pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}$'

        if not re.match(password_pattern, password):
            return """
Password must contain:
- 8+ characters
- Uppercase letter
- Lowercase letter
- Number
- Special character
"""

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )

        if cursor.fetchone():
            conn.close()
            return "Email already registered"

        hashed_password = generate_password_hash(password)

        cursor.execute("""
        INSERT INTO users(fullname,email,password)
        VALUES(%s,%s,%s)
        """, (
            fullname,
            email,
            hashed_password
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")




@app.route("/export")
def export():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT title, amount, category, date
        FROM expenses
        WHERE user_id=%s
        """,
        (session["user_id"],)
    )

    expenses = cursor.fetchall()

    csv_data = "Title,Amount,Category,Date\n"

    for expense in expenses:
        csv_data += f"{expense[0]},{expense[1]},{expense[2]},{expense[3]}\n"

    conn.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            "attachment; filename=expenses.csv"
        }
    )



if __name__ == "__main__":
    app.run()