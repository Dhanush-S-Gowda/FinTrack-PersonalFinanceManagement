from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, mail
from models.user import User
from models.transaction import Transaction
from models.budget import Budget, SavingsGoal, Bill
from config import Config
from datetime import datetime
from werkzeug.routing import BuildError
from sqlalchemy import func, text  # Import text function

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['EXPLAIN_TEMPLATE_LOADING'] = True

    # Initialize extensions
    db.init_app(app)
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register routes
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

            # Fetch the user using raw SQL
            user = db.session.execute(
                text("""
                    SELECT * 
                    FROM user 
                    WHERE email = :email
                """),
                {'email': email}
            ).fetchone()

            # Check if user exists and verify the password
            if user and check_password_hash(user.password, password):
                login_user(user)
                next_page = request.args.get('next')
                flash('Login successful!', 'success')
                return redirect(next_page if next_page else url_for('dashboard'))
            
            flash('Invalid email or password', 'danger')

        return render_template('login.html')  # Render login page if GET request

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

            # Check if the email is already registered
            existing_user = db.session.execute(
                text("""
                    SELECT * 
                    FROM user 
                    WHERE email = :email
                """),
                {'email': email}
            ).fetchone()

            if existing_user:
                flash('Email already registered', 'danger')
                return render_template('auth/register.html')

            # Insert new user into the database
            hashed_password = generate_password_hash(password)
            db.session.execute(
                text("""
                    INSERT INTO user (name, email, password) 
                    VALUES (:name, :email, :password)
                """),
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
        # Get recent transactions
        recent_transactions = Transaction.query.filter_by(user_id=current_user.id)\
            .order_by(Transaction.date.desc())\
            .limit(5).all()
        
        # Calculate total income and expenses using raw SQL
        income = db.session.execute(
            text("SELECT SUM(amount) FROM \"transaction\" WHERE user_id = :user_id AND type = 'income'"),
            {'user_id': current_user.id}
        ).scalar() or 0
        
        expenses = db.session.execute(
            text("SELECT SUM(amount) FROM \"transaction\" WHERE user_id = :user_id AND type = 'expense'"),
            {'user_id': current_user.id}
        ).scalar() or 0
        
        # Calculate balance
        balance = income - expenses
        
        # Get expense categories breakdown
        categories = db.session.execute(
            text("SELECT category, SUM(amount) FROM \"transaction\" WHERE user_id = :user_id AND type = 'expense' GROUP BY category"),
            {'user_id': current_user.id}
        ).fetchall()
        
        return render_template(
            'dashboard/index.html',
            recent_transactions=recent_transactions,
            total_income=income,
            total_expenses=expenses,
            balance=balance,
            categories=categories
        )

    @app.route('/transactions')
    @login_required
    def transactions():
        transactions = db.session.execute(
        text("SELECT * FROM \"transaction\" WHERE user_id = :user_id"),
        {'user_id': current_user.id}
    ).fetchall()
        
        return render_template('dashboard/transactions.html', 
                             transactions=transactions)

    @app.route('/analytics')
    @login_required
    def analytics():
        # Get all transactions for the current user
        transactions = db.session.execute(
            text("SELECT date, amount, type, category FROM \"transaction\" WHERE user_id = :user_id"),
            {'user_id': current_user.id}
        ).fetchall()

        if not transactions:
            return render_template('dashboard/analytics.html', has_data=False)

        # Calculate metrics
        total_income = db.session.execute(
            text("SELECT SUM(amount) FROM \"transaction\" WHERE user_id = :user_id AND type = 'income'"),
            {'user_id': current_user.id}
        ).scalar() or 0
        
        total_expense = db.session.execute(
            text("SELECT SUM(amount) FROM \"transaction\" WHERE user_id = :user_id AND type = 'expense'"),
            {'user_id': current_user.id}
        ).scalar() or 0

        metrics = {
            'total_income': float(total_income),
            'total_expense': float(total_expense),
            'balance': float(total_income - total_expense),
            'transaction_count': len(transactions)
        }

        # Generate AI Insights
        insights = generate_insights(transactions, total_income, total_expense)

        # Prepare data for graphs using raw SQL
        time_series = db.session.execute(
            text("SELECT date, type, SUM(amount) FROM \"transaction\" WHERE user_id = :user_id GROUP BY date, type"),
            {'user_id': current_user.id}
        ).fetchall()

        # Group by day_of_week and type
        day_of_week_summary = db.session.execute(
            text("""
                SELECT strftime('%w', date) AS day_of_week, type, SUM(amount) 
                FROM \"transaction\" 
                WHERE user_id = :user_id 
                GROUP BY day_of_week, type
            """),
            {'user_id': current_user.id}
        ).fetchall()

        # Daily average spending
        daily_avg_spending = db.session.execute(
            text("""
                SELECT date, AVG(amount) 
                FROM \"transaction\" 
                WHERE user_id = :user_id AND type = 'expense' 
                GROUP BY date
            """),
            {'user_id': current_user.id}
        ).fetchall()

        # Category income vs expense
        category_income_expense = db.session.execute(
            text("""
                SELECT category, SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS total_income,
                    SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS total_expense
                FROM \"transaction\"
                WHERE user_id = :user_id
                GROUP BY category
            """),
            {'user_id': current_user.id}
        ).fetchall()

        # Monthly trends
        monthly_trends = db.session.execute(
            text("""
                SELECT strftime('%Y-%m', date) AS month, type, SUM(amount) 
                FROM \"transaction\" 
                WHERE user_id = :user_id 
                GROUP BY month, type
            """),
            {'user_id': current_user.id}
        ).fetchall()

        # Rolling expenses (7-day rolling sum)
        rolling_expenses = db.session.execute(
            text("""
                SELECT date, SUM(amount) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS rolling_sum
                FROM \"transaction\"
                WHERE user_id = :user_id AND type = 'expense'
            """),
            {'user_id': current_user.id}
        ).fetchall()

        # Expense pie chart
        expense_pie_chart = db.session.execute(
            text("""
                SELECT category, SUM(amount) 
                FROM \"transaction\" 
                WHERE user_id = :user_id AND type = 'expense' 
                GROUP BY category
            """),
            {'user_id': current_user.id}
        ).fetchall()

        # Day stack
        day_stack = db.session.execute(
            text("""
                SELECT date, type, SUM(amount) 
                FROM \"transaction\" 
                WHERE user_id = :user_id 
                GROUP BY date, type
            """),
            {'user_id': current_user.id}
        ).fetchall()

        return render_template(
            'dashboard/analytics.html',
            insights=insights,
            metrics=metrics,
            time_series=time_series,
            day_of_week_summary=day_of_week_summary,
            daily_avg_spending=daily_avg_spending,
            category_income_expense=category_income_expense,
            monthly_trends=monthly_trends,
            rolling_expenses=rolling_expenses,
            expense_pie_chart=expense_pie_chart,
            day_stack=day_stack,
            has_data = True
        )

    def generate_insights(user_id):
        insights = []

        # Insight 1: Average Spending
        avg_spending = db.session.execute(
            text("""
                SELECT AVG(amount) 
                FROM \"transaction\" 
                WHERE user_id = :user_id
            """),
            {'user_id': user_id}
        ).scalar() or 0

        optimal_avg_spending = 500  # Example optimal value, replace with actual data
        insights.append({
            'title': 'Average Spending',
            'message': f'Your average spending is ${avg_spending:.2f}. Optimal average spending is ${optimal_avg_spending:.2f}.',
            'comparison': 'above' if avg_spending > optimal_avg_spending else 'below'
        })

        # Insight 2: Top Spending Categories
        top_categories = db.session.execute(
            text("""
                SELECT category, SUM(amount) AS total_amount 
                FROM \"transaction\" 
                WHERE user_id = :user_id 
                GROUP BY category 
                ORDER BY total_amount DESC 
                LIMIT 3
            """),
            {'user_id': user_id}
        ).fetchall()

        insights.append({
            'title': 'Top Spending Categories',
            'message': f'Your top 3 spending categories are: {", ".join(cat[0] for cat in top_categories)}.'
        })

        # Insight 3: Monthly Spending Trends
        monthly_trends = db.session.execute(
            text("""
                SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total_amount 
                FROM \"transaction\" 
                WHERE user_id = :user_id 
                GROUP BY month
            """),
            {'user_id': user_id}
        ).fetchall()

        if monthly_trends:
            max_month = max(monthly_trends, key=lambda x: x[1])
            insights.append({
                'title': 'Monthly Spending Trends',
                'message': f'Your spending has varied over the months, with the highest spending in {max_month[0]} at ${max_month[1]:.2f}.'
            })

        # Insight 4: Expense vs Income Ratio
        total_income = db.session.execute(
            text("""
                SELECT SUM(amount) 
                FROM \"transaction\" 
                WHERE user_id = :user_id AND type = 'income'
            """),
            {'user_id': user_id}
        ).scalar() or 0

        total_expense = db.session.execute(
            text("""
                SELECT SUM(amount) 
                FROM \"transaction\" 
                WHERE user_id = :user_id AND type = 'expense'
            """),
            {'user_id': user_id}
        ).scalar() or 0

        expense_income_ratio = total_expense / total_income if total_income > 0 else 0
        insights.append({
            'title': 'Expense to Income Ratio',
            'message': f'Your expense to income ratio is {expense_income_ratio:.2%}.'
        })

        # Insight 5: Predictive Analysis
        future_expenses = avg_spending * 12  # Simple projection for the next year
        insights.append({
            'title': 'Projected Annual Expenses',
            'message': f'Based on current spending, your projected annual expenses are ${future_expenses:.2f}.'
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
        # Fetch the transaction using raw SQL
        transaction = db.session.execute(
            text("""
                SELECT * 
                FROM "transaction" 
                WHERE id = :id AND user_id = :user_id
            """),
            {'id': id, 'user_id': current_user.id}
        ).fetchone()

        if transaction is None:
            abort(404)  # Transaction not found or does not belong to the user

        # Fetch categories for the current user using raw SQL
        categories = db.session.execute(
            text("""
                SELECT name 
                FROM category 
                WHERE user_id = :user_id
            """),
            {'user_id': current_user.id}
        ).fetchall()

        category_names = [category[0] for category in categories]

        return jsonify({
            'date': transaction.date.strftime('%Y-%m-%d'),
            'type': transaction.type,
            'category': transaction.category,
            'amount': float(transaction.amount),
            'description': transaction.description,
            'categories': category_names  # Include categories in the response if needed
        })

    @app.route('/update_transaction/<int:id>', methods=['GET', 'POST'])
    @login_required
    def update_transaction(id):
        # Fetch the transaction using raw SQL
        transaction = db.session.execute(
            text("""
                SELECT * 
                FROM \"transaction\" 
                WHERE id = :id AND user_id = :user_id
            """),
            {'id': id, 'user_id': current_user.id}
        ).fetchone()

        if transaction is None:
            abort(404)  # Transaction not found or does not belong to the user

        if request.method == 'POST':
            # Update transaction with form data
            new_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
            new_type = request.form.get('type')
            new_category = request.form.get('category')
            new_amount = float(request.form.get('amount'))
            new_description = request.form.get('description')

            # Execute the update query
            db.session.execute(
                text("""
                    UPDATE \"transaction\" 
                    SET date = :date, type = :type, category = :category, 
                        amount = :amount, description = :description 
                    WHERE id = :id AND user_id = :user_id
                """),
                {
                    'date': new_date,
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

        return render_template('edit_transaction.html', transaction=transaction)

    @app.route('/transaction/<int:id>', methods=['DELETE'])
    @login_required
    def delete_transaction(id):
        # Fetch the transaction using raw SQL
        transaction = db.session.execute(
            text("""
                SELECT * 
                FROM \"transaction\" 
                WHERE id = :id AND user_id = :user_id
            """),
            {'id': id, 'user_id': current_user.id}
        ).fetchone()

        if transaction is None:
            abort(404)  # Transaction not found or does not belong to the user

        # Execute the delete query
        db.session.execute(
            text("""
                DELETE FROM \"transaction\" 
                WHERE id = :id AND user_id = :user_id
            """),
            {'id': id, 'user_id': current_user.id}
        )
        db.session.commit()
        return '', 204

    @app.route('/add_transaction', methods=['POST'])
    @login_required
    def add_transaction():
        type = request.form.get('type')
        category = request.form.get('category') or request.form.get('category_new')
        amount = request.form.get('amount')
        date = request.form.get('date')
        description = request.form.get('description')

        # Check if the category is new and save it if it is
        if category:
            existing_category = db.session.execute(
                text("""
                    SELECT * 
                    FROM category 
                    WHERE name = :name AND user_id = :user_id
                """),
                {'name': category, 'user_id': current_user.id}
            ).fetchone()

            # If the category does not exist, insert it
            if not existing_category:
                db.session.execute(
                    text("""
                        INSERT INTO category (name, user_id) 
                        VALUES (:name, :user_id)
                    """),
                    {'name': category, 'user_id': current_user.id}
                )

        # Create new transaction
        db.session.execute(
            text("""
                INSERT INTO "transaction" (type, category, amount, date, description, user_id) 
                VALUES (:type, :category, :amount, :date, :description, :user_id)
            """),
            {
                'type': type,
                'category': category,
                'amount': amount,
                'date': date,
                'description': description,
                'user_id': current_user.id
            }
        )
        db.session.commit()

        flash('Transaction added successfully!', 'success')
        return redirect(url_for('transactions'))

if __name__ == '__main__':
    app = create_app()
    if app is not None:
        with app.app_context():
            db.create_all()
        app.run(debug=True)
    else:
        print("Failed to create the Flask app.")