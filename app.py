from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from io import BytesIO
import xlsxwriter
import os

app = Flask(__name__)

# Konfiguracja dla Render
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-key'),
    SQLALCHEMY_DATABASE_URI=database_url or 'sqlite:///expenses.db',
    SQLALCHEMY_TRACK_MODIFICATIONS=False
)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Model użytkownika
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_accountant = db.Column(db.Boolean, default=False)
    expenses = db.relationship('Expense', backref='user', lazy=True)

# Model kategorii
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    expenses = db.relationship('Expense', backref='category', lazy=True)

# Model wydatku
class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    receipt_data = db.Column(db.LargeBinary)
    receipt_filename = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')

    @property
    def status_color(self):
        return {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger'
        }.get(self.status, 'secondary')

def init_app(app):
    with app.app_context():
        # Tworzenie tabel
        db.create_all()
        
        # Tworzenie domyślnego użytkownika-księgowego, jeśli nie istnieje
        if not User.query.filter_by(username='accountant').first():
            admin = User(
                username='accountant',
                password_hash=generate_password_hash(os.environ.get('INITIAL_ADMIN_PASSWORD', 'Admin123!')),
                is_accountant=True
            )
            db.session.add(admin)
            
        # Dodawanie domyślnych kategorii
        default_categories = [
            ("transport", "Wydatki na transport, paliwo, bilety"),
            ("zakwaterowanie", "Hotele, noclegi"),
            ("wyżywienie", "Posiłki, catering"),
            ("materiały", "Materiały biurowe"),
            ("inne", "Pozostałe wydatki")
        ]
        
        for name, description in default_categories:
            if not Category.query.filter_by(name=name).first():
                category = Category(name=name, description=description)
                db.session.add(category)
        
        try:
            db.session.commit()
            print("Initialization completed successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error during initialization: {e}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    if current_user.is_accountant:
        expenses = Expense.query.order_by(Expense.date.desc())\
            .paginate(page=page, per_page=20, error_out=False)
    else:
        expenses = Expense.query.filter_by(user_id=current_user.id)\
            .order_by(Expense.date.desc())\
            .paginate(page=page, per_page=20, error_out=False)
    return render_template('index.html', expenses=expenses)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash('Nieprawidłowe dane logowania', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    categories = Category.query.all()
    if request.method == 'POST':
        try:
            expense = Expense(
                date=datetime.strptime(request.form['date'], '%Y-%m-%d'),
                amount=float(request.form['amount']),
                description=request.form['description'],
                category_id=int(request.form['category']),
                user_id=current_user.id
            )
            
            if 'receipt' in request.files:
                file = request.files['receipt']
                if file and file.filename:
                    if file.content_length and file.content_length > 5 * 1024 * 1024:
                        flash('Plik jest za duży. Maksymalny rozmiar to 5MB.', 'danger')
                        return redirect(request.url)
                    
                    expense.receipt_data = file.read()
                    expense.receipt_filename = file.filename
            
            db.session.add(expense)
            db.session.commit()
            flash('Wydatek został dodany pomyślnie.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Wystąpił błąd: {str(e)}', 'danger')
            return redirect(request.url)
            
    return render_template('add_expense.html', 
                         categories=categories,
                         today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    
    if not current_user.is_accountant and expense.user_id != current_user.id:
        flash('Brak dostępu', 'danger')
        return redirect(url_for('index'))

    categories = Category.query.all()
    
    if request.method == 'POST':
        try:
            expense.date = datetime.strptime(request.form['date'], '%Y-%m-%d')
            expense.amount = float(request.form['amount'])
            expense.description = request.form['description']
            expense.category_id = int(request.form['category'])
            
            if 'receipt' in request.files:
                file = request.files['receipt']
                if file and file.filename:
                    expense.receipt_data = file.read()
                    expense.receipt_filename = file.filename
            
            db.session.commit()
            flash('Wydatek został zaktualizowany.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Wystąpił błąd: {str(e)}', 'danger')
    
    return render_template('edit_expense.html', 
                         expense=expense,
                         categories=categories)

@app.route('/download_receipt/<int:expense_id>')
@login_required
def download_receipt(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if current_user.is_accountant or expense.user_id == current_user.id:
        if expense.receipt_data:
            return send_file(
                BytesIO(expense.receipt_data),
                download_name=expense.receipt_filename,
                as_attachment=True
            )
    flash('Brak dostępu lub brak pliku', 'danger')
    return redirect(url_for('index'))

@app.route('/reports')
@login_required
def reports():
    if not current_user.is_accountant:
        flash('Brak dostępu', 'danger')
        return redirect(url_for('index'))
    
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    
    total_amount = db.session.query(db.func.sum(Expense.amount))\
        .filter(Expense.date >= start_of_month).scalar() or 0
    
    expense_count = Expense.query\
        .filter(Expense.date >= start_of_month).count()
    
    pending_count = Expense.query\
        .filter_by(status='pending').count()

    categories = db.session.query(
        Category.name,
        db.func.sum(Expense.amount)
    ).join(Expense)\
     .group_by(Category.name)\
     .all()

    timeline = db.session.query(
        db.func.date(Expense.date),
        db.func.sum(Expense.amount)
    ).group_by(db.func.date(Expense.date))\
     .order_by(db.func.date(Expense.date))\
     .all()

    return render_template('reports.html',
                         total_amount=total_amount,
                         expense_count=expense_count,
                         pending_count=pending_count,
                         categories=categories,
                         timeline=timeline)

@app.route('/approve_expense/<int:expense_id>', methods=['POST'])
@login_required
def approve_expense(expense_id):
    if not current_user.is_accountant:
        return jsonify({'error': 'Brak uprawnień'}), 403
    
    expense = Expense.query.get_or_404(expense_id)
    expense.status = 'approved'
    db.session.commit()
    
    return jsonify({
        'message': 'Wydatek zatwierdzony',
        'status': expense.status,
        'status_color': expense.status_color
    })

@app.route('/export_expenses')
@login_required
def export_expenses():
    if not current_user.is_accountant:
        flash('Brak dostępu', 'danger')
        return redirect(url_for('index'))

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()

    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#f0f0f0',
        'border': 1
    })
    
    date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})
    amount_format = workbook.add_format({'num_format': '#,##0.00 zł'})

    headers = ['Data', 'Użytkownik', 'Kategoria', 'Opis', 'Kwota', 'Status']
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)

    expenses = Expense.query.order_by(Expense.date.desc()).all()
    for row, expense in enumerate(expenses, start=1):
        worksheet.write_datetime(row, 0, expense.date, date_format)
        worksheet.write(row, 1, expense.user.username)
        worksheet.write(row, 2, expense.category.name if expense.category else '')
        worksheet.write(row, 3, expense.description)
        worksheet.write_number(row, 4, expense.amount, amount_format)
        worksheet.write(row, 5, expense.status)

    worksheet.autofilter(0, 0, len(expenses), len(headers)-1)
    worksheet.set_column(0, 0, 12)
    worksheet.set_column(1, 1, 15)
    worksheet.set_column(2, 2, 15)
    worksheet.set_column(3, 3, 40)
    worksheet.set_column(4, 4, 12)
    worksheet.set_column(5, 5, 10)

    workbook.close()
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'wydatki_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

# Inicjalizacja przy starcie
init_app(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
