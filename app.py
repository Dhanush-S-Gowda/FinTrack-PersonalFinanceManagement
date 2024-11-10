from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from config import Config
from datetime import datetime, timedelta
from sqlalchemy import text
from werkzeug.routing import BuildError
from datetime import datetime, date  # Add date to your imports


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize the database
    db.init_app(app)

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.execute(
            text("SELECT id, name, email FROM user WHERE id = :user_id"),
            {'user_id': user_id}
        ).mappings().fetchone()

        if user:
            return User(id=user['id'], name=user['name'], email=user['email'])
        return None

    with app.app_context():
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(150) NOT NULL,
                email VARCHAR(150) UNIQUE NOT NULL CHECK (email LIKE '%_@__%.__%'),
                password VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))

        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS "transaction" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type VARCHAR(50) NOT NULL,
                category VARCHAR(50) NOT NULL,
                amount FLOAT NOT NULL CHECK (amount > 0),
                date TIMESTAMP NOT NULL,
                description TEXT,
                user_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES user (id) ON DELETE CASCADE
            )
        '''))

        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS category (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user (id) ON DELETE CASCADE,
                UNIQUE(name, user_id)
            )
        '''))

        db.session.commit()

    class User(UserMixin):
        def __init__(self, id, name, email):
            self.id = id
            self.name = name
            self.email = email

    @app.route('/add_dummy_data')
    @login_required
    def add_dummy_data():
        # Ensure only the specified user can access this route
        if current_user.email != 'dhanushsgowda277@gmail.com':
            abort(403)

        # Find the user's ID
        user = db.session.execute(
            text('SELECT id FROM user WHERE email = :email'),
            {'email': current_user.email}
        ).fetchone()

        if user is None:
            return 'User not found', 404

        user_id = user.id  # Since fetchone() returns a Row object with named attributes

        # Dummy transactions to insert
        transactions = [
            {
                'type': 'income',
                'category': 'Salary',
                'amount': 5000,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'description': 'Monthly Salary',
                'user_id': user_id
            },
            {
                'type': 'expense',
                'category': 'Groceries',
                'amount': 150,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'description': 'Weekly groceries shopping',
                'user_id': user_id
            },
            {
                'type': 'expense',
                'category': 'Utilities',
                'amount': 100,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'description': 'Electricity bill',
                'user_id': user_id
            },
            {
                'type': 'expense',
                'category': 'Entertainment',
                'amount': 75,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'description': 'Movie tickets',
                'user_id': user_id
            },
            {
                'type': 'income',
                'category': 'Freelance',
                'amount': 800,
                'date': (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'),
                'description': 'Freelance project payment',
                'user_id': user_id
            },
            {
                'type': 'expense',
                'category': 'Travel',
                'amount': 300,
                'date': (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'),
                'description': 'Weekend trip',
                'user_id': user_id
            },
        ]

        for txn in transactions:
            db.session.execute(
                text('''
                    INSERT INTO "transaction" (type, category, amount, date, description, user_id)
                    VALUES (:type, :category, :amount, :date, :description, :user_id)
                '''), txn
            )
        db.session.commit()

        flash('Dummy data added successfully!', 'success')
        return redirect(url_for('transactions'))
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))


    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')

            user = db.session.execute(
                text("SELECT id, name, email, password FROM user WHERE email = :email"),
                {'email': email}
            ).mappings().fetchone()

            if user and check_password_hash(user['password'], password):
                user_obj = User(id=user['id'], name=user['name'], email=user['email'])
                login_user(user_obj)
                flash('Login successful!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page if next_page else url_for('dashboard'))

            flash('Invalid email or password', 'danger')

        return render_template('auth/login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            if password != confirm_password:
                flash('Passwords do not match', 'danger')
                return render_template('auth/register.html')

            existing_user = db.session.execute(
                text("SELECT * FROM user WHERE email = :email"),
                {'email': email}
            ).fetchone()

            if existing_user:
                flash('Email already registered', 'danger')
                return render_template('auth/register.html')

            hashed_password = generate_password_hash(password)
            db.session.execute(
                text("INSERT INTO user (name, email, password) VALUES (:name, :email, :password)"),
                {'name': name, 'email': email, 'password': hashed_password}
            )
            db.session.commit()

            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))

        return render_template('auth/register.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('login'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        recent_transactions = db.session.execute(
            text('SELECT * FROM "transaction" WHERE user_id = :user_id ORDER BY date DESC LIMIT 5'),
            {'user_id': current_user.id}
        ).mappings().fetchall()

        recent_transactions = [dict(transaction) for transaction in recent_transactions]

        for transaction in recent_transactions:
            if isinstance(transaction['date'], str):
                transaction['date'] = datetime.fromisoformat(transaction['date'])
            else:
                transaction['date'] = transaction['date']

        income = db.session.execute(
            text('SELECT SUM(amount) FROM "transaction" WHERE user_id = :user_id AND type = \'income\''),
            {'user_id': current_user.id}
        ).scalar() or 0

        expenses = db.session.execute(
            text('SELECT SUM(amount) FROM "transaction" WHERE user_id = :user_id AND type = \'expense\''),
            {'user_id': current_user.id}
        ).scalar() or 0

        balance = income - expenses

        categories = db.session.execute(
            text('SELECT category, SUM(amount) AS total_amount FROM "transaction" WHERE user_id = :user_id AND type = \'expense\' GROUP BY category'),
            {'user_id': current_user.id}
        ).mappings().fetchall()

        categories = [dict(category) for category in categories]

        return render_template(
            'dashboard/index.html',
            recent_transactions=recent_transactions,
            total_income=income,
            total_expenses=expenses,
            balance=balance,
            categories=categories
        )

    # app.py
    @app.route('/transactions')
    @login_required
    def transactions():
        transactions = db.session.execute(
            text('SELECT * FROM "transaction" WHERE user_id = :user_id'),
            {'user_id': current_user.id}
        ).mappings().fetchall()

        transactions = [dict(transaction) for transaction in transactions]

        for transaction in transactions:
            if isinstance(transaction['date'], str):
                transaction['date'] = datetime.fromisoformat(transaction['date'])
            else:
                transaction['date'] = transaction['date']

        # Fetch categories for the Add Transaction modal
        categories = db.session.execute(
            text('SELECT name FROM category WHERE user_id = :user_id'),
            {'user_id': current_user.id}
        ).mappings().fetchall()

        categories = [category['name'] for category in categories]

        # Pass 'date' to the template
        return render_template(
            'dashboard/transactions.html',
            transactions=transactions,
            categories=categories,
            date=date  # Pass the date class
        )


    @app.route('/analytics')
    @login_required
    def analytics():
        user_id = current_user.id

        # Check if the user has any transactions
        total_transactions = db.session.execute(
            text('SELECT COUNT(*) FROM "transaction" WHERE user_id = :user_id'),
            {'user_id': user_id}
        ).scalar()

        if total_transactions == 0:
            return render_template('dashboard/analytics.html', has_data=False)

        # 1. Time Series Line Chart Data
        time_series_rows = db.session.execute(
            text('''
                SELECT date(date) as date,
                       SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as income,
                       SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as expense
                FROM "transaction"
                WHERE user_id = :user_id
                GROUP BY date(date)
                ORDER BY date(date)
            '''),
            {'user_id': user_id}
        ).fetchall()

        time_series = {
            'date': [row[0] for row in time_series_rows],
            'income': [row[1] or 0 for row in time_series_rows],
            'expense': [row[2] or 0 for row in time_series_rows]
        }

        # 2. Stacked Bar Chart for Income and Expense by Day of the Week
        day_of_week_rows = db.session.execute(
            text('''
                SELECT strftime('%w', date) as day_of_week,
                       SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as income,
                       SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as expense
                FROM "transaction"
                WHERE user_id = :user_id
                GROUP BY day_of_week
                ORDER BY day_of_week
            '''),
            {'user_id': user_id}
        ).fetchall()

        # Map day numbers to day names
        day_number_to_name = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

        day_of_week_summary = {
            'day_of_week': [day_number_to_name[int(row[0])] for row in day_of_week_rows],
            'income': [row[1] or 0 for row in day_of_week_rows],
            'expense': [row[2] or 0 for row in day_of_week_rows]
        }

        # 3. Average Daily Spending Over Time
        daily_avg_spending_rows = db.session.execute(
            text('''
                SELECT date(date) as date, AVG(amount) as avg_amount
                FROM "transaction"
                WHERE user_id = :user_id AND type = 'expense'
                GROUP BY date(date)
                ORDER BY date(date)
            '''),
            {'user_id': user_id}
        ).fetchall()

        daily_avg_spending = {
            'date': [row[0] for row in daily_avg_spending_rows],
            'avg_amount': [row[1] or 0 for row in daily_avg_spending_rows]
        }

        # 4. Income vs. Expense by Category
        category_income_expense_rows = db.session.execute(
            text('''
                SELECT category,
                       SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as income,
                       SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as expense
                FROM "transaction"
                WHERE user_id = :user_id
                GROUP BY category
                ORDER BY category
            '''),
            {'user_id': user_id}
        ).fetchall()

        category_income_expense = {
            'category': [row[0] for row in category_income_expense_rows],
            'income': [row[1] or 0 for row in category_income_expense_rows],
            'expense': [row[2] or 0 for row in category_income_expense_rows]
        }

        # 5. Monthly Trends
        monthly_trends_rows = db.session.execute(
            text('''
                SELECT strftime('%Y-%m', date) as month,
                       SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as income,
                       SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as expense
                FROM "transaction"
                WHERE user_id = :user_id
                GROUP BY month
                ORDER BY month
            '''),
            {'user_id': user_id}
        ).fetchall()

        monthly_trends = {
            'month': [row[0] for row in monthly_trends_rows],
            'income': [row[1] or 0 for row in monthly_trends_rows],
            'expense': [row[2] or 0 for row in monthly_trends_rows]
        }

        # 6. Rolling 7-Day Expenses
        # SQLite supports window functions in version >= 3.25
        rolling_expenses_rows = db.session.execute(
            text('''
                SELECT date(date) as date,
                       SUM(amount) OVER (
                           ORDER BY date(date)
                           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                       ) as rolling_sum
                FROM "transaction"
                WHERE user_id = :user_id AND type = 'expense'
                ORDER BY date(date)
            '''),
            {'user_id': user_id}
        ).fetchall()

        rolling_expenses = {
            'date': [row[0] for row in rolling_expenses_rows],
            'rolling_sum': [row[1] or 0 for row in rolling_expenses_rows]
        }

        # 7. Expense Pie Chart
        expense_pie_chart_rows = db.session.execute(
            text('''
                SELECT category, SUM(amount) as amount
                FROM "transaction"
                WHERE user_id = :user_id AND type = 'expense'
                GROUP BY category
                ORDER BY category
            '''),
            {'user_id': user_id}
        ).fetchall()

        expense_pie_chart = {
            'category': [row[0] for row in expense_pie_chart_rows],
            'amount': [row[1] or 0 for row in expense_pie_chart_rows]
        }

        # 8. Daily Stack Chart (using time_series data)
        day_stack = time_series

        # 9. Scatter Day Pattern
        scatter_day_pattern_rows = db.session.execute(
            text('''
                SELECT strftime('%w', date) as day_of_week, amount
                FROM "transaction"
                WHERE user_id = :user_id AND type = 'expense'
                ORDER BY date(date)
            '''),
            {'user_id': user_id}
        ).fetchall()

        scatter_day_pattern = {
            'day_of_week': [day_number_to_name[int(row[0])] for row in scatter_day_pattern_rows],
            'amount': [row[1] or 0 for row in scatter_day_pattern_rows]
        }

        # Compute metrics
        total_income = db.session.execute(
            text('SELECT SUM(amount) FROM "transaction" WHERE user_id = :user_id AND type = \'income\''),
            {'user_id': user_id}
        ).scalar() or 0

        total_expense = db.session.execute(
            text('SELECT SUM(amount) FROM "transaction" WHERE user_id = :user_id AND type = \'expense\''),
            {'user_id': user_id}
        ).scalar() or 0

        balance = total_income - total_expense

        transaction_count = db.session.execute(
            text('SELECT COUNT(*) FROM "transaction" WHERE user_id = :user_id'),
            {'user_id': user_id}
        ).scalar()

        return render_template(
            'dashboard/analytics.html',
            insights=generate_insights(user_id),
            metrics={
                'total_income': total_income,
                'total_expense': total_expense,
                'balance': balance,
                'transaction_count': transaction_count
            },
            time_series=time_series,
            day_of_week_summary=day_of_week_summary,
            daily_avg_spending=daily_avg_spending,
            category_income_expense=category_income_expense,
            monthly_trends=monthly_trends,
            rolling_expenses=rolling_expenses,
            expense_pie_chart=expense_pie_chart,
            day_stack=day_stack,
            scatter_day_pattern=scatter_day_pattern,
            has_data=True
        )

    def generate_insights(user_id):
        insights = []

        # Insight 1: Average Spending
        avg_spending = db.session.execute(
            text('SELECT AVG(amount) FROM "transaction" WHERE user_id = :user_id AND type = \'expense\''),
            {'user_id': user_id}
        ).scalar() or 0

        insights.append({
            'title': 'Average Spending',
            'message': f'Your average spending is ${avg_spending:.2f}. Consider reducing it if necessary.'
        })

        # Insight 2: Top Spending Categories
        top_categories_rows = db.session.execute(
            text('''
                SELECT category, SUM(amount) as total_amount
                FROM "transaction"
                WHERE user_id = :user_id AND type = 'expense'
                GROUP BY category
                ORDER BY total_amount DESC
                LIMIT 3
            '''),
            {'user_id': user_id}
        ).fetchall()

        top_categories = [row[0] for row in top_categories_rows]
        if top_categories:
            insights.append({
                'title': 'Top Spending Categories',
                'message': f'Your top 3 spending categories are: {", ".join(top_categories)}.'
            })

        # Insight 3: Income vs. Expense Trend
        total_income = db.session.execute(
            text('SELECT SUM(amount) FROM "transaction" WHERE user_id = :user_id AND type = \'income\''),
            {'user_id': user_id}
        ).scalar() or 0

        total_expense = db.session.execute(
            text('SELECT SUM(amount) FROM "transaction" WHERE user_id = :user_id AND type = \'expense\''),
            {'user_id': user_id}
        ).scalar() or 0

        if total_expense > total_income:
            insights.append({
                'title': 'Spending Alert',
                'message': 'Your expenses exceed your income. Consider reviewing your spending habits.'
            })
        else:
            insights.append({
                'title': 'Good Job',
                'message': 'Your income exceeds your expenses. Keep up the good financial management!'
            })

        # Insight 4: Monthly Expense Change
        # Get the total expense for this month and last month
        today = date.today()
        first_day_this_month = today.replace(day=1)
        last_month_last_day = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_month_last_day.replace(day=1)

        expenses_this_month = db.session.execute(
            text('''
                SELECT SUM(amount) FROM "transaction"
                WHERE user_id = :user_id AND type = 'expense'
                AND date(date) BETWEEN :first_day_this_month AND :today
            '''),
            {'user_id': user_id, 'first_day_this_month': first_day_this_month.strftime('%Y-%m-%d'), 'today': today.strftime('%Y-%m-%d')}
        ).scalar() or 0

        expenses_last_month = db.session.execute(
            text('''
                SELECT SUM(amount) FROM "transaction"
                WHERE user_id = :user_id AND type = 'expense'
                AND date(date) BETWEEN :first_day_last_month AND :last_day_last_month
            '''),
            {'user_id': user_id, 'first_day_last_month': first_day_last_month.strftime('%Y-%m-%d'), 'last_day_last_month': last_month_last_day.strftime('%Y-%m-%d')}
        ).scalar() or 0

        if expenses_this_month > expenses_last_month:
            insights.append({
                'title': 'Increased Spending',
                'message': 'Your spending has increased compared to the previous month.'
            })
        elif expenses_this_month < expenses_last_month:
            insights.append({
                'title': 'Reduced Spending',
                'message': 'Good job! Your spending has decreased compared to the previous month.'
            })
        else:
            insights.append({
                'title': 'Stable Spending',
                'message': 'Your spending is similar to the previous month.'
            })

        # Insight 5: Frequent Expenses
        frequent_transactions_row = db.session.execute(
            text('''
                SELECT description, COUNT(*) as freq
                FROM "transaction"
                WHERE user_id = :user_id AND type = 'expense'
                GROUP BY description
                HAVING freq > 3
                ORDER BY freq DESC
                LIMIT 1
            '''),
            {'user_id': user_id}
        ).fetchone()

        if frequent_transactions_row:
            insights.append({
                'title': 'Frequent Expenses',
                'message': f'You have made {frequent_transactions_row[1]} transactions on "{frequent_transactions_row[0]}". Consider if these are necessary.'
            })

        return insights

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    @app.errorhandler(BuildError)
    def handle_build_error(e):
        flash('An error occurred while accessing that page.', 'danger')
        return redirect(url_for('dashboard'))

    @app.route('/transaction/<int:id>', methods=['GET'])
    @login_required
    def get_transaction(id):
        transaction = db.session.execute(
            text('SELECT * FROM "transaction" WHERE id = :id AND user_id = :user_id'),
            {'id': id, 'user_id': current_user.id}
        ).mappings().fetchone()

        if transaction is None:
            abort(404)

        transaction = dict(transaction)
        # Ensure date is formatted as string
        if isinstance(transaction['date'], datetime):
            transaction['date'] = transaction['date'].strftime('%Y-%m-%d')

        return jsonify(transaction)

    @app.route('/update_transaction/<int:id>', methods=['POST'])
    @login_required
    def update_transaction(id):
        # Fetch the transaction
        transaction = db.session.execute(
            text('SELECT * FROM "transaction" WHERE id = :id AND user_id = :user_id'),
            {'id': id, 'user_id': current_user.id}
        ).fetchone()

        if transaction is None:
            abort(404)

        # Get data from form
        new_date_str = request.form.get('date')
        new_date = datetime.strptime(new_date_str, '%Y-%m-%d')
        new_type = request.form.get('type')
        new_category = request.form.get('category')
        new_amount = float(request.form.get('amount'))
        new_description = request.form.get('description')

        # Update the transaction
        db.session.execute(
            text('''
                UPDATE "transaction"
                SET date = :date, type = :type, category = :category, amount = :amount, description = :description
                WHERE id = :id AND user_id = :user_id
            '''),
            {
                'date': new_date.isoformat(),
                'type': new_type,
                'category': new_category,
                'amount': new_amount,
                'description': new_description,
                'id': id,
                'user_id': current_user.id
            }
        )
        db.session.commit()
        flash('Transaction updated successfully!', 'success')
        return redirect(url_for('transactions'))

    @app.route('/transaction/<int:id>', methods=['DELETE'])
    @login_required
    def delete_transaction(id):
        transaction = db.session.execute(
            text('SELECT * FROM "transaction" WHERE id = :id AND user_id = :user_id'),
            {'id': id, 'user_id': current_user.id}
        ).mappings().fetchone()

        if transaction is None:
            abort(404)

        db.session.execute(
            text('DELETE FROM "transaction" WHERE id = :id AND user_id = :user_id'),
            {'id': id, 'user_id': current_user.id}
        )
        db.session.commit()
        return '', 204

    @app.route('/add_transaction', methods=['POST'])
    @login_required
    def add_transaction():
        type = request.form.get('type')
        category = request.form.get('category')
        amount = request.form.get('amount')
        date_str = request.form.get('date')
        description = request.form.get('description')

        # If 'Add New Category' is selected
        if category == 'new_category':
            category = request.form.get('category_new')
        if float(amount) <= 0:
            flash('Amount must be greater than 0.', 'danger')
            return redirect(url_for("transactions"))

        if category:
            existing_category = db.session.execute(
                text('SELECT * FROM category WHERE name = :name AND user_id = :user_id'),
                {'name': category, 'user_id': current_user.id}
            ).fetchone()

            if not existing_category:
                db.session.execute(
                    text('INSERT INTO category (name, user_id) VALUES (:name, :user_id)'),
                    {'name': category, 'user_id': current_user.id}
                )

        # Parse date and ensure it's in the correct format
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        date_iso = date_obj.isoformat()

        db.session.execute(
            text('''
                INSERT INTO "transaction" (type, category, amount, date, description, user_id)
                VALUES (:type, :category, :amount, :date, :description, :user_id)
            '''),
            {
                'type': type,
                'category': category,
                'amount': amount,
                'date': date_iso,
                'description': description,
                'user_id': current_user.id
            }
        )
        db.session.commit()
        flash('Transaction added successfully!', 'success')
        return redirect(url_for('transactions'))

    return app

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        pass  # Tables are already created in create_app
    app.run(debug=True)
